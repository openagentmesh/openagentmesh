"""low-alt.heli: warm Responder agent driven by ActionFleetAgent (D-41/D-46, SCN-05).

Phase 2 promotes the Phase 1 cold stub into a warm Responder. The handler
delegates entirely to the shared ``ActionFleetAgent`` base class, which
owns the single-writer task (D-41), the simulation lifecycle (transit ->
drop -> return), and the per-transition status pubsub on
``mesh.action.heli.{instance_id}.status`` (D-45).

Subclass-specific bits:

  - ``zone="low-alt"`` / ``fleet_type="heli"``.
  - Speed and action duration tuned via ``HELI_SPEED_KM_S`` and
    ``HELI_ACTION_DURATION_S`` in ``demos/wildfire/core/config.py``.
  - ``_make_status()`` returns a ``HeliStatus`` with linearly-draining
    ``water_remaining_pct`` during the "acting" leg (1.0 -> 0.0) and a
    refill ramp on the "returning" leg back to 1.0 by the time the heli
    is "free" again.
  - ``_act()`` logs a loud "dropping water at ..." line for demo narration.

Multiple instances spawned by the orchestrator share the queue group
``q.low-alt.heli`` automatically per ``src/openagentmesh/_mesh.py``, so
first-available-wins is preserved at the dispatch boundary.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time

from pydantic import BaseModel

from demos.wildfire.core.config import (
    HELI_ACTION_DURATION_S,
    HELI_SPEED_KM_S,
    HQ,
)
from demos.wildfire.core.contracts import (
    ActionState,
    Coords,
    DispatchOrder,
    HeliStatus,
)
from demos.wildfire.fleet._action import ActionFleetAgent
from openagentmesh import AgentMesh

_log = logging.getLogger("wildfire.heli")


# ---------------------------------------------------------------------------
# Subclass
# ---------------------------------------------------------------------------


class HeliAgent(ActionFleetAgent):
    """Aerial water-bomber. Warm Responder per D-46."""

    def __init__(self, mesh: AgentMesh) -> None:
        super().__init__(
            mesh,
            zone="low-alt",
            fleet_type="heli",
            speed_km_s=HELI_SPEED_KM_S,
            action_duration_s=HELI_ACTION_DURATION_S,
            home=HQ,
        )

    def _make_status(
        self,
        *,
        state: ActionState,
        order_id: str | None,
        coords: Coords,
    ) -> BaseModel:
        # Water gauge: full while transiting, drains during the drop, refills
        # on return. Simple piecewise mapping per state — refined further if
        # the demo asks for finer-grained gauges.
        if state in ("free", "dispatched", "en_route", "on_site"):
            water_pct = 1.0
        elif state == "acting":
            water_pct = 0.0  # dropping; treat as "spent" snapshot
        elif state == "returning":
            water_pct = 0.5  # mid-refill on the way home
        else:
            water_pct = 1.0
        return HeliStatus(
            instance_id=self.mesh.instance_id,
            order_id=order_id,
            state=state,
            coords=coords,
            water_remaining_pct=water_pct,
            timestamp=time.time(),
        )

    async def _act(self, order: DispatchOrder) -> None:
        _log.info(
            "heli %s dropping water at (%.2f, %.2f) for order %s",
            self.mesh.instance_id, order.target_coords.x,
            order.target_coords.y, order.order_id,
        )
        await asyncio.sleep(self.action_duration_s)


# ---------------------------------------------------------------------------
# Process entry point: `python -m demos.wildfire.fleet.heli`
# ---------------------------------------------------------------------------


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    agent = HeliAgent(mesh)
    agent.register_handler(
        mesh,
        name="low-alt.heli",
        description=(
            "Aerial water-bomber. Accepts DispatchOrder, performs water drop, "
            "returns DispatchAck."
        ),
    )

    async with mesh:
        await agent.start()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            await agent.stop()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
