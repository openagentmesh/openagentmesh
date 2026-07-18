"""Mesh-native observability: the ``mesh.observe`` namespace (ADR-0048 v1).

Log events are plain NATS messages on ``mesh.logs.{name}`` — ephemeral by
design (no JetStream, no retention). What gets published is controlled by
the ``mesh-observability`` KV bucket: a ``global`` key and per-agent keys
(the dotted agent name), per-agent winning. Hosts watch the bucket and apply
changes live; consumers use :meth:`Observe.logs` to tail.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Literal, cast

from ._models import LogEvent, ObserveConfig
from ._subjects import compute_log_subject

if TYPE_CHECKING:
    from ._mesh import AgentMesh

# Numeric severity for gating. "off" is a threshold only, never an event level.
LEVELS: dict[str, int] = {"debug": 10, "info": 20, "warn": 30, "error": 40, "off": 100}

GLOBAL_KEY = "global"

LogLevel = Literal["debug", "info", "warn", "error", "off"]


def _parse_level(raw: bytes | None) -> LogLevel | None:
    """Extract a valid log_level from a stored config value, else None."""
    if not raw:
        return None
    try:
        level = json.loads(raw).get("log_level")
    except Exception:
        return None
    return cast("LogLevel", level) if level in LEVELS else None


class Observe:
    """``mesh.observe``: consume log events and manage observability config."""

    def __init__(self, mesh: AgentMesh) -> None:
        self._mesh = mesh

    async def logs(
        self, agent: str | None = None, *, level: str | None = None
    ) -> AsyncIterator[LogEvent]:
        """Tail log events, mesh-wide or for one agent.

        Yields :class:`LogEvent` as events arrive; runs until the caller
        breaks out. *level* filters to that severity and above.
        """
        if level is not None and level not in LEVELS:
            raise ValueError(f"Unknown level '{level}'. Choose from: {', '.join(LEVELS)}.")
        threshold = LEVELS[level] if level else 0
        subject = compute_log_subject(agent) if agent else "mesh.logs.>"

        queue: asyncio.Queue = asyncio.Queue()

        async def _on_msg(msg) -> None:
            queue.put_nowait(msg)

        sub = await self._mesh._conn.subscribe(subject, cb=_on_msg)
        await self._mesh._conn.flush()
        try:
            while True:
                msg = await queue.get()
                try:
                    event = LogEvent.model_validate_json(msg.data)
                except Exception:
                    continue  # tolerate foreign payloads on the subject
                if LEVELS.get(event.level, 0) >= threshold:
                    yield event
        finally:
            with contextlib.suppress(Exception):
                await sub.unsubscribe()

    async def get(self, agent: str) -> ObserveConfig:
        """Effective config for *agent*: per-agent key > global > default."""
        kv = self._mesh._observe_kv_required
        for key, source in ((agent, "agent"), (GLOBAL_KEY, "global")):
            try:
                entry = await kv.get(key)
            except Exception:
                continue
            level = _parse_level(entry.value)
            if level is not None:
                return ObserveConfig(log_level=level, source=source)
        return ObserveConfig()

    async def set(self, agent: str, *, log_level: str) -> None:
        """Set the per-agent log level (applies live via KV watch)."""
        await self._put(agent, log_level)

    async def set_global(self, *, log_level: str) -> None:
        """Set the mesh-wide default log level."""
        await self._put(GLOBAL_KEY, log_level)

    async def _put(self, key: str, log_level: str) -> None:
        if log_level not in LEVELS:
            raise ValueError(
                f"Unknown log_level '{log_level}'. Choose from: {', '.join(LEVELS)}."
            )
        kv = self._mesh._observe_kv_required
        await kv.put(key, json.dumps({"log_level": log_level}).encode())


__all__ = ["LEVELS", "GLOBAL_KEY", "LogLevel", "Observe"]
