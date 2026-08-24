"""Unit tests for the warm low-altitude heli agent (SCN-05, D-41/D-44/D-45/D-46).

Phase 2 promotes the Phase 1 cold stub to a warm Responder driven by the
shared ``ActionFleetAgent`` base class (plan 02-02 Task 1). The Phase 1
"phase 1 stub" assertion and the heartbeat_loop assertion are retired:
the warm handler returns ``DispatchAck(accepted=True)`` and the
single-writer loop in ActionFleetAgent absorbs the heartbeat (D-41).

Asserted invariants:

  - Module exposes ``HeliAgent`` (subclass of ``ActionFleetAgent``) and
    async ``_main()``.
  - Source text registers ``AgentSpec(name="low-alt.heli", ...)``.
  - Source text contains zero references to ``heartbeat_loop`` (collapsed
    into the writer per D-41) or to dropped pubsub artefacts (FireSpawn,
    ThermalGrid, mesh.environment.thermal).
  - ``mesh.publish`` IS allowed in Phase 2 (status pubsub on transitions).
  - Live boot test: ``mesh.call("low-alt.heli", DispatchOrder(...))``
    returns ``accepted=True`` within 1 s; status pubsub fires on
    ``mesh.action.heli.>.status``.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from pathlib import Path

import pytest

from openagentmesh import AgentMesh

from demos.wildfire.core.contracts import (
    Coords,
    DispatchOrder,
)

heli = pytest.importorskip(
    "demos.wildfire.fleet.heli",
    reason="demos.wildfire.fleet.heli not yet on disk.",
)


# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_heli_module_exposes_heli_agent_class():
    assert hasattr(heli, "HeliAgent")


def test_heli_agent_subclasses_action_fleet_agent():
    from demos.wildfire.fleet._action import ActionFleetAgent

    assert issubclass(heli.HeliAgent, ActionFleetAgent)


def test_main_is_async_coroutine_function():
    assert inspect.iscoroutinefunction(heli._main)


# ---------------------------------------------------------------------------
# Source-text invariants
# ---------------------------------------------------------------------------


_HELI_PATH = Path(heli.__file__)


def test_heli_module_registers_low_alt_heli_agent_spec():
    text = _HELI_PATH.read_text()
    assert 'name="low-alt.heli"' in text


def test_heli_module_does_not_use_heartbeat_loop():
    """heartbeat_loop is collapsed into ActionFleetAgent's writer (D-41)."""
    text = _HELI_PATH.read_text()
    assert "heartbeat_loop" not in text


def test_heli_module_does_not_carry_phase1_stub_marker():
    """Warm handler is no longer a stub."""
    text = _HELI_PATH.read_text()
    assert "phase 1 stub" not in text.lower()


def test_heli_module_subclasses_action_fleet_agent_in_source():
    text = _HELI_PATH.read_text()
    assert "class HeliAgent(ActionFleetAgent)" in text


@pytest.mark.parametrize(
    "needle",
    [
        "subject_source",
        "kv_source",
        "ThermalGrid",
        "FireSpawn",
        "FireSuppress",
        "mesh.environment.thermal",
        "mesh.fire.spawn",
        "mesh.fire.suppress",
    ],
)
def test_heli_module_does_not_reference_dropped_artefacts(needle: str):
    text = _HELI_PATH.read_text()
    assert needle not in text, (
        f"{needle!r} should not appear in {_HELI_PATH.name}"
    )


@pytest.mark.parametrize("needle", ["bucket=", "prefix=", "model="])
def test_heli_module_does_not_use_aspirational_kwargs(needle: str):
    text = _HELI_PATH.read_text()
    assert needle not in text, f"{needle!r} is not a real SDK kwarg (A-09)"


# ---------------------------------------------------------------------------
# Live boot tests against AgentMesh.local()
# ---------------------------------------------------------------------------


def _make_order(target: Coords) -> DispatchOrder:
    return DispatchOrder(
        order_id="o-heli-1",
        target_coords=target,
        priority="med",
        operator_id="op-1",
        issued_at=time.time(),
    )


async def test_heli_dispatch_returns_accepted_ack():
    """``mesh.call("low-alt.heli", DispatchOrder(...))`` returns accepted ack within 1 s."""
    async with AgentMesh.local() as mesh:
        agent = heli.HeliAgent(mesh)
        agent.register_handler(
            mesh,
            name="low-alt.heli",
            description="Aerial water-bomber.",
        )
        async with agent:
            t0 = time.monotonic()
            result = await mesh.call(
                "low-alt.heli",
                _make_order(Coords(x=1.0, y=1.0)),
                timeout=1.0,
            )
            elapsed = time.monotonic() - t0
            assert elapsed < 1.0, f"call took {elapsed:.3f}s"
            # mesh.call returns the dict-decoded JSON of DispatchAck.
            assert result["accepted"] is True
            assert result["instance_id"] == mesh.instance_id
            assert result["eta_seconds"] is not None
            assert result["eta_seconds"] > 0


async def test_heli_publishes_status_on_dispatch():
    """At least one HeliStatus message arrives on mesh.action.heli.{id}.status."""
    async with AgentMesh.local() as mesh:
        agent = heli.HeliAgent(mesh)
        agent.register_handler(
            mesh,
            name="low-alt.heli",
            description="Aerial water-bomber.",
        )

        observed_states: list[str] = []
        first_msg = asyncio.Event()

        async def _on_status(msg) -> None:
            payload = json.loads(msg.data.decode())
            observed_states.append(payload["state"])
            first_msg.set()

        sub = await mesh._nc.subscribe(
            f"mesh.action.heli.{mesh.instance_id}.status",
            cb=_on_status,
        )

        async with agent:
            try:
                ack = await mesh.call(
                    "low-alt.heli",
                    _make_order(Coords(x=0.5, y=0.5)),
                    timeout=2.0,
                )
                assert ack["accepted"] is True
                await asyncio.wait_for(first_msg.wait(), timeout=6.0)
            finally:
                await sub.unsubscribe()

        assert len(observed_states) >= 1
        # All observed states must be valid ActionState members.
        valid = {
            "free", "dispatched", "en_route", "on_site",
            "acting", "returning",
        }
        assert set(observed_states).issubset(valid), (
            f"unexpected states: {observed_states}"
        )
