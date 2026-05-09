"""ground.ffunit: warm Responder agent driven by ActionFleetAgent (D-41/D-46, SCN-06).

Phase 2 promotes the Phase 1 cold stub into a warm Responder. The handler
delegates entirely to the shared ``ActionFleetAgent`` base class, which
owns the single-writer task (D-41), the simulation lifecycle (transit ->
suppress -> return), and the per-transition status pubsub on
``mesh.action.ffunit.{instance_id}.status`` (D-45).

Subclass-specific bits:

  - ``zone="ground"`` / ``fleet_type="ffunit"``.
  - Speed and action duration tuned via ``FFUNIT_SPEED_KM_S`` and
    ``FFUNIT_ACTION_DURATION_S`` in ``demos/wildfire/core/config.py``.
  - ``_make_status()`` returns a ``FFUnitStatus`` with
    ``reserves_remaining_pct`` draining during the "acting" leg, and
    ``persons_at_risk_observed`` set to ``order.persons_estimated`` once
    on-site (the operator's estimate echoed back as the ffunit's
    on-the-ground observation).
  - ``_act()`` logs a "suppressing fire at ..." line for demo narration.

Three instances spawned by the orchestrator share the queue group
``q.ground.ffunit`` automatically per ``src/openagentmesh/_mesh.py``,
preserving first-available-wins routing at the dispatch boundary.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time

from pydantic import BaseModel

from demos.wildfire.core.config import (
    FFUNIT_ACTION_DURATION_S,
    FFUNIT_SPEED_KM_S,
    HQ,
)
from demos.wildfire.core.contracts import (
    ActionState,
    Coords,
    DispatchOrder,
    FFUnitStatus,
)
from demos.wildfire.fleet._action import ActionFleetAgent
from openagentmesh import AgentMesh

_log = logging.getLogger("wildfire.ffunit")


# ---------------------------------------------------------------------------
# Subclass
# ---------------------------------------------------------------------------


class FFUnitAgent(ActionFleetAgent):
    """Ground firefighter unit. Warm Responder per D-46."""

    def __init__(self, mesh: AgentMesh) -> None:
        super().__init__(
            mesh,
            zone="ground",
            fleet_type="ffunit",
            speed_km_s=FFUNIT_SPEED_KM_S,
            action_duration_s=FFUNIT_ACTION_DURATION_S,
            home=HQ,
        )

    def _make_status(
        self,
        *,
        state: ActionState,
        order_id: str | None,
        coords: Coords,
    ) -> BaseModel:
        # Reserves gauge: full pre-action, drained mid-action, partly refilled
        # on return. Coarse piecewise mapping for the v1 demo.
        if state in ("free", "dispatched", "en_route", "on_site"):
            reserves_pct = 1.0
        elif state == "acting":
            reserves_pct = 0.0
        elif state == "returning":
            reserves_pct = 0.5
        else:
            reserves_pct = 1.0
        # persons_at_risk_observed: surface the operator's estimate to medevac
        # on/after on_site (rationale: the ffunit is the boots-on-ground
        # observer; downstream systems read this off the status feed).
        if (
            state in ("on_site", "acting", "returning")
            and self._order is not None
        ):
            persons_observed = self._order.persons_estimated
        else:
            persons_observed = 0
        return FFUnitStatus(
            instance_id=self.mesh.instance_id,
            order_id=order_id,
            state=state,
            coords=coords,
            reserves_remaining_pct=reserves_pct,
            persons_at_risk_observed=persons_observed,
            timestamp=time.time(),
        )

    async def _act(self, order: DispatchOrder) -> None:
        _log.info(
            "ffunit %s suppressing fire at (%.2f, %.2f) for order %s",
            self.mesh.instance_id, order.target_coords.x,
            order.target_coords.y, order.order_id,
        )
        await asyncio.sleep(self.action_duration_s)


# ---------------------------------------------------------------------------
# Process entry point: `python -m demos.wildfire.fleet.ffunit`
# ---------------------------------------------------------------------------


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    agent = FFUnitAgent(mesh)
    agent.register_handler(
        mesh,
        name="ground.ffunit",
        description=(
            "Ground firefighter unit. Accepts DispatchOrder, simulates "
            "suppression, returns DispatchAck."
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
