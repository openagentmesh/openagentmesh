"""Unit tests for the shared ``ActionFleetAgent`` base class (D-41, D-42, D-44, D-45, D-46).

The base class drives the action-fleet lifecycle (transit -> action -> return)
behind a single-writer task that owns all KV writes for the agent's own
``FleetMemberState`` record. Subclasses (heli / ffunit / medevac in plan
02-02 / 02-03) override:

  - ``zone``, ``fleet_type`` (per-fleet identity)
  - ``speed_km_s``, ``action_duration_s`` (per-fleet ETA constants)
  - ``_make_status(...)`` (returns the per-fleet status BaseModel)

This test file pins the public surface and the lifecycle invariants. A
synthetic ``_TestAgent`` subclass parametrises a minimal status BaseModel
so the base-class behaviour can be exercised without dragging the heli /
ffunit / medevac subclasses into the test fixture.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from pydantic import BaseModel

from demos.wildfire.core.contracts import (
    ActionState,
    Coords,
    DispatchOrder,
    FleetMemberState,
)
from demos.wildfire.core.keys import FLEET_PREFIX
from openagentmesh import AgentMesh

# Module under test (created by Task 1 GREEN).
af = pytest.importorskip(
    "demos.wildfire.fleet._action",
    reason="demos.wildfire.fleet._action not yet on disk (plan 02-02 Task 1).",
)


# ---------------------------------------------------------------------------
# Synthetic subclass for base-class tests
# ---------------------------------------------------------------------------


class _TestStatus(BaseModel):
    """Minimal status payload used by the synthetic test subclass."""

    instance_id: str
    order_id: str | None
    state: ActionState
    coords: Coords
    timestamp: float


class _TestAgent(af.ActionFleetAgent):
    """Synthetic ActionFleetAgent for base-class tests.

    Parametrised at __init__ so individual tests can tune speed and action
    duration to keep simulations short (~1 s).
    """

    def __init__(
        self,
        mesh: AgentMesh,
        *,
        speed_km_s: float = 5.0,
        action_duration_s: float = 0.2,
        home: Coords | None = None,
    ) -> None:
        super().__init__(
            mesh,
            zone="low-alt",
            fleet_type="heli",  # reuse a real zone/type so fleet_key validates
            speed_km_s=speed_km_s,
            action_duration_s=action_duration_s,
            home=home,
        )

    def _make_status(
        self,
        *,
        state: ActionState,
        order_id: str | None,
        coords: Coords,
    ) -> BaseModel:
        return _TestStatus(
            instance_id=self.mesh.instance_id,
            order_id=order_id,
            state=state,
            coords=coords,
            timestamp=time.time(),
        )


def _make_order(target: Coords, *, order_id: str = "o-1") -> DispatchOrder:
    return DispatchOrder(
        order_id=order_id,
        target_coords=target,
        priority="med",
        operator_id="op-1",
        issued_at=time.time(),
    )


# ---------------------------------------------------------------------------
# Public surface (module shape)
# ---------------------------------------------------------------------------


def test_action_fleet_agent_class_exists():
    assert hasattr(af, "ActionFleetAgent")


# ---------------------------------------------------------------------------
# Lifecycle tests against AgentMesh.local()
# ---------------------------------------------------------------------------


async def test_handle_returns_ack_quickly():
    """Handler must return DispatchAck without awaiting the simulation (D-42)."""
    async with AgentMesh.local() as mesh:
        agent = _TestAgent(mesh, speed_km_s=5.0, action_duration_s=0.2)
        agent.register_handler(
            mesh, name="low-alt.heli", description="test agent",
        )
        async with agent:
            order = _make_order(Coords(x=3.0, y=4.0))
            t0 = time.monotonic()
            ack = await agent.handle(order)
            elapsed = time.monotonic() - t0
            assert elapsed < 0.5, f"handle should return < 0.5s; took {elapsed:.3f}s"
            assert ack.accepted is True
            assert ack.instance_id == mesh.instance_id
            assert ack.eta_seconds is not None
            # ETA = sqrt(3^2 + 4^2) / 5 + 0.2 = 1.0 + 0.2 = 1.2
            assert abs(ack.eta_seconds - 1.2) < 0.1, (
                f"ETA should be ~1.2s; got {ack.eta_seconds}"
            )


async def test_handle_rejects_when_busy():
    """Second concurrent dispatch must return accepted=False reason='busy' (D-44)."""
    async with AgentMesh.local() as mesh:
        agent = _TestAgent(mesh, speed_km_s=1.0, action_duration_s=2.0)
        agent.register_handler(
            mesh, name="low-alt.heli", description="test agent",
        )
        async with agent:
            ack1 = await agent.handle(_make_order(Coords(x=1.0, y=1.0), order_id="o-1"))
            assert ack1.accepted is True
            # Immediately dispatch a second order while sim still running.
            ack2 = await agent.handle(_make_order(Coords(x=2.0, y=2.0), order_id="o-2"))
            assert ack2.accepted is False
            assert ack2.reason == "busy"
            assert ack2.instance_id == mesh.instance_id


async def test_simulation_publishes_status_on_each_transition():
    """Every state transition publishes a per-fleet status to mesh.action.{type}.{id}.status (D-45)."""
    async with AgentMesh.local() as mesh:
        # Tune for fast simulation: 5 km/s + 0.2 s action.
        agent = _TestAgent(mesh, speed_km_s=5.0, action_duration_s=0.2)
        agent.register_handler(
            mesh, name="low-alt.heli", description="test agent",
        )

        observed_states: list[str] = []
        ready = asyncio.Event()

        async def _on_status(msg) -> None:
            import json
            payload = json.loads(msg.data.decode())
            observed_states.append(payload["state"])
            if payload["state"] == "free":
                ready.set()

        sub = await mesh._conn.subscribe(
            f"mesh.action.heli.{mesh.instance_id}.status",
            cb=_on_status,
        )

        async with agent:
            try:
                ack = await agent.handle(_make_order(Coords(x=1.0, y=1.0)))
                assert ack.accepted is True
                # ETA ~ sqrt(2)/5 + 0.2 = ~0.48 s; allow 5 s grace.
                await asyncio.wait_for(ready.wait(), timeout=5.0)
            finally:
                await sub.unsubscribe()

        # Expect every transition: dispatched, en_route, on_site, acting, returning, free.
        expected = {"dispatched", "en_route", "on_site", "acting", "returning", "free"}
        assert expected.issubset(set(observed_states)), (
            f"missing transitions; observed={observed_states}"
        )
        assert len(observed_states) >= 5


async def test_writer_writes_fleetmemberstate_on_idle_when_no_transition():
    """The writer task ticks last_updated even with no transitions (collapsed heartbeat per D-41)."""
    async with AgentMesh.local() as mesh:
        # Force tight heartbeat-equivalent idle interval so the test stays
        # under a couple of seconds even if HEARTBEAT_INTERVAL_S is 1.0.
        agent = _TestAgent(mesh)
        agent.register_handler(
            mesh, name="low-alt.heli", description="test agent",
        )
        async with agent:
            # No dispatch. Wait for one idle write.
            await asyncio.sleep(1.5)
            entries = await mesh.kv.list(f"{FLEET_PREFIX}.low-alt.heli.>")
            entries = [e for e in entries if e.value]
            assert len(entries) >= 1, (
                f"writer should write idle FleetMemberState; got {len(entries)}"
            )
            rec = FleetMemberState.model_validate_json(entries[0].value)
            assert rec.state == "free"
            assert rec.current_assignment is None
            assert time.time() - rec.last_updated < 2.0


async def test_eta_formula():
    """ETA = distance / speed + action_duration (D-43)."""
    async with AgentMesh.local() as mesh:
        # Agent at HQ (0,0); target (3,4) => distance 5; speed 1.0; action 2.0 -> eta 7.0
        agent = _TestAgent(
            mesh,
            speed_km_s=1.0,
            action_duration_s=2.0,
            home=Coords(x=0.0, y=0.0),
        )
        eta = agent._eta(_make_order(Coords(x=3.0, y=4.0)))
        assert abs(eta - 7.0) < 0.01, f"expected ETA=7.0; got {eta}"


async def test_state_transitions_to_free_after_simulation():
    """After the simulation completes, the agent returns to free + clears its sim task."""
    async with AgentMesh.local() as mesh:
        agent = _TestAgent(mesh, speed_km_s=5.0, action_duration_s=0.2)
        agent.register_handler(
            mesh, name="low-alt.heli", description="test agent",
        )
        async with agent:
            ack = await agent.handle(_make_order(Coords(x=1.0, y=1.0)))
            assert ack.accepted is True
            # ETA ~ 0.48 s; wait generously.
            await asyncio.sleep(2.0)
            assert agent._state == "free"
            assert agent._sim_task is None
            assert agent._order is None
