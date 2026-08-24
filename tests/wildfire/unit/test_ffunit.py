"""Unit tests for the warm ground ffunit agent (SCN-06, D-41/D-44/D-45/D-46).

Phase 2 promotes the Phase 1 cold stub to a warm Responder driven by the
shared ``ActionFleetAgent`` base class (plan 02-02 Task 1). The Phase 1
"phase 1 stub" assertion and the heartbeat_loop assertion are retired:
the warm handler returns ``DispatchAck(accepted=True)`` and the
single-writer loop in ActionFleetAgent absorbs the heartbeat (D-41).

Asserted invariants:

  - Module exposes ``FFUnitAgent`` (subclass of ``ActionFleetAgent``) and
    async ``_main()``.
  - Source text registers ``AgentSpec(name="ground.ffunit", ...)``.
  - Source text contains zero references to ``heartbeat_loop`` or to
    dropped pubsub artefacts.
  - ``mesh.publish`` IS allowed in Phase 2 (status pubsub on transitions).
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

ffunit = pytest.importorskip(
    "demos.wildfire.fleet.ffunit",
    reason="demos.wildfire.fleet.ffunit not yet on disk.",
)


# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_ffunit_module_exposes_ffunit_agent_class():
    assert hasattr(ffunit, "FFUnitAgent")


def test_ffunit_agent_subclasses_action_fleet_agent():
    from demos.wildfire.fleet._action import ActionFleetAgent

    assert issubclass(ffunit.FFUnitAgent, ActionFleetAgent)


def test_main_is_async_coroutine_function():
    assert inspect.iscoroutinefunction(ffunit._main)


# ---------------------------------------------------------------------------
# Source-text invariants
# ---------------------------------------------------------------------------


_FFUNIT_PATH = Path(ffunit.__file__)


def test_ffunit_module_registers_ground_ffunit_agent_spec():
    text = _FFUNIT_PATH.read_text()
    assert 'name="ground.ffunit"' in text


def test_ffunit_module_does_not_use_heartbeat_loop():
    """heartbeat_loop is collapsed into ActionFleetAgent's writer (D-41)."""
    text = _FFUNIT_PATH.read_text()
    assert "heartbeat_loop" not in text


def test_ffunit_module_does_not_carry_phase1_stub_marker():
    """Warm handler is no longer a stub."""
    text = _FFUNIT_PATH.read_text()
    assert "phase 1 stub" not in text.lower()


def test_ffunit_module_subclasses_action_fleet_agent_in_source():
    text = _FFUNIT_PATH.read_text()
    assert "class FFUnitAgent(ActionFleetAgent)" in text


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
def test_ffunit_module_does_not_reference_dropped_artefacts(needle: str):
    text = _FFUNIT_PATH.read_text()
    assert needle not in text, (
        f"{needle!r} should not appear in {_FFUNIT_PATH.name}"
    )


@pytest.mark.parametrize("needle", ["bucket=", "prefix=", "model="])
def test_ffunit_module_does_not_use_aspirational_kwargs(needle: str):
    text = _FFUNIT_PATH.read_text()
    assert needle not in text, f"{needle!r} is not a real SDK kwarg (A-09)"


# ---------------------------------------------------------------------------
# Live boot tests against AgentMesh.local()
# ---------------------------------------------------------------------------


def _make_order(target: Coords) -> DispatchOrder:
    return DispatchOrder(
        order_id="o-ffunit-1",
        target_coords=target,
        priority="med",
        operator_id="op-1",
        issued_at=time.time(),
    )


async def test_ffunit_dispatch_returns_accepted_ack():
    """``mesh.call("ground.ffunit", DispatchOrder(...))`` returns accepted ack within 1 s."""
    async with AgentMesh.local() as mesh:
        agent = ffunit.FFUnitAgent(mesh)
        agent.register_handler(
            mesh,
            name="ground.ffunit",
            description="Ground firefighter unit.",
        )
        async with agent:
            t0 = time.monotonic()
            result = await mesh.call(
                "ground.ffunit",
                _make_order(Coords(x=0.5, y=0.5)),
                timeout=1.0,
            )
            elapsed = time.monotonic() - t0
            assert elapsed < 1.0, f"call took {elapsed:.3f}s"
            assert result["accepted"] is True
            assert result["instance_id"] == mesh.instance_id
            assert result["eta_seconds"] is not None
            assert result["eta_seconds"] > 0


async def test_ffunit_publishes_status_on_dispatch():
    """At least one FFUnitStatus message arrives on mesh.action.ffunit.{id}.status."""
    async with AgentMesh.local() as mesh:
        agent = ffunit.FFUnitAgent(mesh)
        agent.register_handler(
            mesh,
            name="ground.ffunit",
            description="Ground firefighter unit.",
        )

        observed_states: list[str] = []
        first_msg = asyncio.Event()

        async def _on_status(msg) -> None:
            payload = json.loads(msg.data.decode())
            observed_states.append(payload["state"])
            first_msg.set()

        sub = await mesh._nc.subscribe(
            f"mesh.action.ffunit.{mesh.instance_id}.status",
            cb=_on_status,
        )

        async with agent:
            try:
                ack = await mesh.call(
                    "ground.ffunit",
                    _make_order(Coords(x=0.2, y=0.2)),
                    timeout=2.0,
                )
                assert ack["accepted"] is True
                await asyncio.wait_for(first_msg.wait(), timeout=6.0)
            finally:
                await sub.unsubscribe()

        assert len(observed_states) >= 1
        valid = {
            "free", "dispatched", "en_route", "on_site",
            "acting", "returning",
        }
        assert set(observed_states).issubset(valid)
