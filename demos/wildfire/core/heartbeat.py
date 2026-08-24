"""Shared 1 Hz fleet heartbeat loop (D-09, D-10, A-08).

Every fleet member (uav, drone, heli, ffunit) calls this in a background
task so the admin UI can derive liveness from the freshness of
``wildfire.fleet.{zone}.{type}.{instance_id}``.

A single missed put is logged and swallowed: a transient KV hiccup must not
kill the fleet member's main work. The loop exits cleanly on
``asyncio.CancelledError`` -- the heartbeat key is intentionally NOT deleted
on shutdown so the admin UI's reader-side staleness (D-10) surfaces the
offline state within ``LIVENESS_STALENESS_S``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from openagentmesh import AgentMesh

from .config import HEARTBEAT_INTERVAL_S
from .contracts import Coords, FleetMemberState, FleetMemberState_StateLit
from .keys import fleet_key

_log = logging.getLogger("wildfire.heartbeat")


async def heartbeat_loop(
    mesh: AgentMesh,
    *,
    zone: str,
    fleet_type: str,
    get_state: Callable[[], FleetMemberState_StateLit],
    get_coords: Callable[[], Coords],
    get_assignment: Callable[[], str | None] = lambda: None,
    interval_s: float = HEARTBEAT_INTERVAL_S,
) -> None:
    """Write a ``FleetMemberState`` to KV every ``interval_s`` seconds until cancelled.

    ``zone`` and ``fleet_type`` are typed as ``str`` rather than the underlying
    ``Literal`` aliases so callers don't need to thread the type aliases
    through; the ``FleetMemberState`` constructor enforces validity via
    Pydantic.
    """
    key = fleet_key(zone, fleet_type, mesh.instance_id)
    try:
        while True:
            try:
                record = FleetMemberState(
                    instance_id=mesh.instance_id,
                    zone=zone,
                    fleet_type=fleet_type,
                    coords=get_coords(),
                    state=get_state(),
                    current_assignment=get_assignment(),
                    last_updated=time.time(),
                )
                await mesh.kv.put_model(key, record)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.warning("heartbeat write failed for %s: %s", key, e)
            await asyncio.sleep(interval_s)
    except asyncio.CancelledError:
        return
