"""ground.medevac: warm Responder agent driven by ActionFleetAgent (D-41/D-46, SCN-07).

Phase 2 closes the cascade with the third action-fleet member: medevac.
The handler delegates to the shared ``ActionFleetAgent`` base class for
lifecycle, single-writer KV, and per-transition status pubsub on
``mesh.action.medevac.{instance_id}.status`` (D-45).

Subclass-specific bits:

  - ``zone="ground"`` / ``fleet_type="medevac"``.
  - Speed and action duration tuned via ``MEDEVAC_SPEED_KM_S`` and
    ``MEDEVAC_ACTION_DURATION_S`` in ``demos/wildfire/core/config.py``.
  - ``capacity_max = MEDEVAC_CAPACITY_MAX`` (default 4 persons).
  - Per-instance counter ``self._capacity_used`` (starts at 0). Increments
    by ``order.persons_estimated`` on entering "acting"; resets to 0 on
    re-entering "free" (drop-off at the single holding point per
    medevac.md "Holding point: single for v1"). Both transitions ride the
    ``_on_transition`` hook so the next status pubsub frame reflects the
    update.
  - Capacity rejection: if ``persons_estimated + self._capacity_used >
    self.capacity_max`` the handler returns
    ``DispatchAck(accepted=False, reason="capacity")`` BEFORE delegating
    to ``super().handle(order)``. This is checked first so that a fully
    loaded medevac declines new pickups even if it would otherwise be
    "free" (e.g. between a returning pickup and the writer marking it
    free again — defensive ordering).
  - ``_make_status()`` returns a ``MedevacStatus`` with the live
    ``capacity_used`` and ``capacity_max`` so dashboards can render the
    fill gauge.
  - ``_act()`` logs an "extracting persons at ..." line for demo narration.

Three instances spawned by the orchestrator share the queue group
``q.ground.medevac`` automatically per ``src/openagentmesh/_mesh.py``,
preserving first-available-wins routing at the dispatch boundary
(per ADR-0049 + capacity-aware reject).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time

from pydantic import BaseModel

from demos.wildfire.core.config import (
    HQ,
    MEDEVAC_ACTION_DURATION_S,
    MEDEVAC_CAPACITY_MAX,
    MEDEVAC_SPEED_KM_S,
)
from demos.wildfire.core.contracts import (
    ActionState,
    Coords,
    DispatchAck,
    DispatchOrder,
    MedevacStatus,
)
from demos.wildfire.fleet._action import ActionFleetAgent
from openagentmesh import AgentMesh

_log = logging.getLogger("wildfire.medevac")


# ---------------------------------------------------------------------------
# Subclass
# ---------------------------------------------------------------------------


class MedevacAgent(ActionFleetAgent):
    """Ground medevac unit. Warm Responder per D-46 with capacity rejection."""

    def __init__(self, mesh: AgentMesh) -> None:
        super().__init__(
            mesh,
            zone="ground",
            fleet_type="medevac",
            speed_km_s=MEDEVAC_SPEED_KM_S,
            action_duration_s=MEDEVAC_ACTION_DURATION_S,
            home=HQ,
        )
        self.capacity_max: int = MEDEVAC_CAPACITY_MAX
        self._capacity_used: int = 0

    # ------------------------------------------------------------------
    # Capacity rejection (medevac-specific) wrapped around the base handle.
    # ------------------------------------------------------------------

    async def handle(self, order: DispatchOrder) -> DispatchAck:
        """Reject on capacity overflow; otherwise delegate to base (busy / accept)."""
        if order.persons_estimated + self._capacity_used > self.capacity_max:
            return DispatchAck(
                accepted=False,
                instance_id=self.mesh.instance_id,
                eta_seconds=None,
                reason="capacity",
            )
        return await super().handle(order)

    # ------------------------------------------------------------------
    # Status payload + transition hook (capacity bookkeeping)
    # ------------------------------------------------------------------

    def _make_status(
        self,
        *,
        state: ActionState,
        order_id: str | None,
        coords: Coords,
    ) -> BaseModel:
        return MedevacStatus(
            instance_id=self.mesh.instance_id,
            order_id=order_id,
            state=state,
            coords=coords,
            capacity_used=self._capacity_used,
            capacity_max=self.capacity_max,
            timestamp=time.time(),
        )

    def _on_transition(
        self,
        *,
        state: ActionState,
        order_id: str | None,
    ) -> None:
        # Increment on entering 'acting' (extraction begins): use the in-flight
        # order's persons_estimated so capacity_used reflects who is now aboard.
        if state == "acting" and self._order is not None:
            self._capacity_used += self._order.persons_estimated
        # Reset on re-entering 'free' (drop-off at single holding point per
        # medevac.md "Holding point: single for v1"). The next dispatch sees
        # an empty bay.
        elif state == "free":
            self._capacity_used = 0

    # ------------------------------------------------------------------
    # In-place action body — narration only.
    # ------------------------------------------------------------------

    async def _act(self, order: DispatchOrder) -> None:
        _log.info(
            "medevac %s extracting %d person(s) at (%.2f, %.2f) for order %s",
            self.mesh.instance_id, order.persons_estimated,
            order.target_coords.x, order.target_coords.y, order.order_id,
        )
        await asyncio.sleep(self.action_duration_s)


# ---------------------------------------------------------------------------
# Build helper (returns the agent so callers can manage start/stop)
# ---------------------------------------------------------------------------


def build_agent(mesh: AgentMesh) -> MedevacAgent:
    """Construct a MedevacAgent and bind its dispatch handler.

    Returns the agent instance so callers (tests / _main) can run
    ``await agent.start()`` / ``await agent.stop()`` themselves. The
    description is consumed by the LLM tool-selection layer per the
    contract description rule (state what it does + when to use it).
    """
    agent = MedevacAgent(mesh)
    agent.register_handler(
        mesh,
        name="ground.medevac",
        description=(
            "Ground medevac unit. Accepts DispatchOrder with "
            "persons_estimated, drives to coords, extracts persons, "
            "returns to base. Rejects with reason=\"capacity\" if "
            "persons_estimated would exceed capacity_max - capacity_used. "
            "Use when persons need extraction; not for fire suppression."
        ),
    )
    return agent


# ---------------------------------------------------------------------------
# Process entry point: `python -m demos.wildfire.fleet.medevac`
# ---------------------------------------------------------------------------


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    agent = build_agent(mesh)

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
