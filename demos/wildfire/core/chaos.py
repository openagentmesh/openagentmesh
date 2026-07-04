"""Chaos-kill listener shared by every fleet member (Phase 4).

The scenario UI's fleet popover publishes a ``ChaosKill`` on
``mesh.chaos.kill.{instance_id}``. The targeted process dies HARD
(``os._exit``): no KV cleanup, no graceful drain, exactly like a crash.
The admin UI's heartbeat staleness (D-10) turns the liveness dot red
within ``LIVENESS_STALENESS_S`` seconds, and the briefer's stale-assignment
watchdog reclaims any detection the dead unit was surveying.

Kept out of :mod:`demos.wildfire.core.heartbeat` on purpose: the heartbeat
must never die with a subscription error, while this listener is
best-effort by design.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from openagentmesh import AgentMesh

_log = logging.getLogger("wildfire.chaos")

CHAOS_KILL_PREFIX = "mesh.chaos.kill"


def chaos_kill_subject(instance_id: str) -> str:
    return f"{CHAOS_KILL_PREFIX}.{instance_id}"


async def chaos_kill_listener(
    mesh: AgentMesh,
    *,
    _exit: Callable[[int], None] = os._exit,
) -> None:
    """Block on ``mesh.chaos.kill.{instance_id}`` and hard-exit on receipt.

    Run as a background task next to the heartbeat. ``_exit`` is injectable
    so tests can observe the kill without dying.
    """
    subject = chaos_kill_subject(mesh.instance_id)
    async for frame in mesh.subscribe(subject=subject):
        _log.warning("chaos kill received (%s); dying uncleanly", frame)
        _exit(1)
