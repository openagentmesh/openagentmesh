"""Mesh health monitor (ADR-0016).

Subscribes to NATS ``$SYS.ACCOUNT.*.DISCONNECT`` advisories and turns host
disconnects into catalog/registry cleanup plus ``mesh.death.{name}`` notices.
Hosted by the mesh lifecycle owner: ``AgentMesh.local()`` runs one in-process,
``oam mesh up`` runs one next to the server. Not part of every SDK client —
``$SYS`` access is privileged, and N monitors would race on deregistration.

Two connections, because NATS accounts isolate subjects: a system-account
connection reads advisories; a regular ``AgentMesh`` connection (APP account)
performs deregistration and publishes death notices.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any

import nats

from ._mesh import AgentMesh
from ._models import DeathNotice
from ._subjects import compute_death_subject

_log = logging.getLogger("openagentmesh")

_HOST_PREFIX = "oam-host-"
DISCONNECT_ADVISORIES = "$SYS.ACCOUNT.*.DISCONNECT"


class HealthMonitor:
    """Watches disconnect advisories and cleans up after dead agent hosts."""

    def __init__(
        self,
        url: str,
        *,
        sys_url: str | None = None,
        sys_creds: str | None = None,
        creds: str | None = None,
    ):
        self._mesh = AgentMesh(url, creds=creds)
        self._sys_url = sys_url or url
        self._sys_creds = sys_creds
        self._sys_nc: Any | None = None
        self._sub: Any | None = None

    async def start(self) -> None:
        await self._mesh.__aenter__()
        options: dict[str, Any] = {}
        if self._sys_creds is not None:
            options["user_credentials"] = self._sys_creds
        self._sys_nc = await nats.connect(self._sys_url, **options)
        self._sub = await self._sys_nc.subscribe(
            DISCONNECT_ADVISORIES, cb=self._on_advisory
        )
        await self._sys_nc.flush()

    async def stop(self) -> None:
        if self._sub is not None:
            with suppress(Exception):
                await self._sub.unsubscribe()
            self._sub = None
        if self._sys_nc is not None:
            with suppress(Exception):
                await self._sys_nc.close()
            self._sys_nc = None
        await self._mesh.__aexit__(None, None, None)

    async def __aenter__(self) -> HealthMonitor:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    async def run_forever(self) -> None:
        """Serve until cancelled. For CLI hosting."""
        await asyncio.Event().wait()

    # --- advisory handling ---

    async def _on_advisory(self, msg: Any) -> None:
        try:
            advisory = json.loads(msg.data)
        except Exception:
            return
        client_name = (advisory.get("client") or {}).get("name", "")
        if not client_name.startswith(_HOST_PREFIX):
            return  # not an AgentMesh host connection
        instance_id = client_name[len(_HOST_PREFIX):]
        try:
            await self._handle_host_death(instance_id)
        except Exception as e:  # advisory handling must never kill the monitor
            _log.warning("health monitor failed to process death of %s: %s", instance_id, e)

    async def _handle_host_death(self, instance_id: str) -> None:
        instances_kv = self._mesh._instances_kv
        assert instances_kv is not None
        try:
            entry = await instances_kv.get(instance_id)
            agents: list[str] = json.loads(entry.value or b"{}").get("agents", [])
        except Exception:
            return  # gracefully shut down (key already deleted) or not a host

        with suppress(Exception):
            await instances_kv.delete(instance_id)

        survivors = await self._mesh._agents_served_by_live_instances()
        for name in agents:
            if name in survivors:
                continue  # another instance still serves this agent: scale-down
            await self._mesh._deregister_agent_record(name)
            notice = DeathNotice(
                agent=name, reason="disconnect", instance_id=instance_id
            )
            await self._mesh._conn.publish(
                compute_death_subject(name),
                notice.model_dump_json().encode(),
            )
            _log.info("death notice published for '%s' (host %s)", name, instance_id)


__all__ = ["HealthMonitor", "DISCONNECT_ADVISORIES"]
