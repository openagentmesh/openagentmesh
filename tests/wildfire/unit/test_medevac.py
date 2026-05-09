"""Unit tests for the warm ground medevac agent (SCN-07, D-41/D-44/D-45/D-46).

Phase 2 lands the third action-fleet member: ``ground.medevac``. Like heli
and ffunit, MedevacAgent subclasses the shared ``ActionFleetAgent`` base
class (plan 02-02). Medevac is the only fleet that mutates ``capacity_used``
per dispatch and the only fleet with capacity rejection
(``DispatchAck(accepted=False, reason="capacity")``) per medevac.md.

Asserted invariants:

  - Module exposes ``MedevacAgent`` (subclass of ``ActionFleetAgent``),
    ``build_agent``, and async ``_main()``.
  - Source text registers ``AgentSpec(name="ground.medevac", ...)``.
  - Source text contains zero references to ``heartbeat_loop`` (collapsed
    into the writer per D-41) or to dropped pubsub artefacts.
  - Source text contains zero references to forbidden SDK kwargs
    (``bucket=`` / ``prefix=`` / ``model=``) per A-09.
  - No ``subject_source`` / ``kv_source`` calls (medevac is a Responder).
  - Live boot test: ``mesh.call("ground.medevac", DispatchOrder(...))``
    returns ``accepted=True`` within 1 s; status pubsub fires on
    ``mesh.action.medevac.>.status``.
  - Capacity rejection: when ``persons_estimated + capacity_used >
    capacity_max``, the handler returns ``DispatchAck(accepted=False,
    reason="capacity")``.
  - Concurrent dispatch reject: a second order while busy returns
    ``reason="busy"`` (inherited from the base class).
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

medevac = pytest.importorskip(
    "demos.wildfire.fleet.medevac",
    reason="demos.wildfire.fleet.medevac not yet on disk.",
)


# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_medevac_module_exposes_medevac_agent_class():
    assert hasattr(medevac, "MedevacAgent")


def test_medevac_module_exposes_build_agent():
    assert hasattr(medevac, "build_agent")
    assert callable(medevac.build_agent)


def test_medevac_agent_subclasses_action_fleet_agent():
    from demos.wildfire.fleet._action import ActionFleetAgent

    assert issubclass(medevac.MedevacAgent, ActionFleetAgent)


def test_main_is_async_coroutine_function():
    assert inspect.iscoroutinefunction(medevac._main)


# ---------------------------------------------------------------------------
# Source-text invariants
# ---------------------------------------------------------------------------


_MEDEVAC_PATH = Path(medevac.__file__)


def test_medevac_module_registers_ground_medevac_agent_spec():
    text = _MEDEVAC_PATH.read_text()
    assert 'name="ground.medevac"' in text


def test_medevac_module_does_not_use_heartbeat_loop():
    """heartbeat_loop is collapsed into ActionFleetAgent's writer (D-41)."""
    text = _MEDEVAC_PATH.read_text()
    assert "heartbeat_loop" not in text


def test_medevac_module_subclasses_action_fleet_agent_in_source():
    text = _MEDEVAC_PATH.read_text()
    assert "class MedevacAgent(ActionFleetAgent)" in text


def test_medevac_module_no_sources():
    """Medevac is a Responder; no subject_source / kv_source calls."""
    text = _MEDEVAC_PATH.read_text()
    assert "subject_source(" not in text
    assert "kv_source(" not in text


def test_medevac_module_uses_capacity_reason():
    """Reject path uses reason="capacity" per medevac.md."""
    text = _MEDEVAC_PATH.read_text()
    assert 'reason="capacity"' in text


@pytest.mark.parametrize(
    "needle",
    [
        "ThermalGrid",
        "FireSpawn",
        "FireSuppress",
        "mesh.environment.thermal",
        "mesh.fire.spawn",
        "mesh.fire.suppress",
    ],
)
def test_medevac_module_does_not_reference_dropped_artefacts(needle: str):
    text = _MEDEVAC_PATH.read_text()
    assert needle not in text, (
        f"{needle!r} should not appear in {_MEDEVAC_PATH.name}"
    )


@pytest.mark.parametrize("needle", ["bucket=", "prefix=", "model="])
def test_medevac_module_does_not_use_aspirational_kwargs(needle: str):
    text = _MEDEVAC_PATH.read_text()
    assert needle not in text, f"{needle!r} is not a real SDK kwarg (A-09)"


def test_medevac_module_no_locks_or_cas_on_own_record():
    """Single-writer pattern (D-41): no asyncio.Lock, no try_cas / cas() on own record."""
    text = _MEDEVAC_PATH.read_text()
    assert "asyncio.Lock" not in text
    assert "try_cas" not in text
    # Filter out comments to avoid grep on the rationale line.
    code_lines = [
        line for line in text.splitlines()
        if not line.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "cas(" not in code


# ---------------------------------------------------------------------------
# Live boot tests against AgentMesh.local()
# ---------------------------------------------------------------------------


def _make_order(
    target: Coords,
    *,
    order_id: str = "o-medevac-1",
    persons: int = 1,
) -> DispatchOrder:
    return DispatchOrder(
        order_id=order_id,
        target_coords=target,
        priority="med",
        operator_id="op-1",
        issued_at=time.time(),
        persons_estimated=persons,
    )


async def test_medevac_dispatch_returns_accepted_ack():
    """``mesh.call("ground.medevac", DispatchOrder(...))`` returns accepted ack within 1 s."""
    async with AgentMesh.local() as mesh:
        agent = medevac.MedevacAgent(mesh)
        agent.register_handler(
            mesh,
            name="ground.medevac",
            description="Ground medevac.",
        )
        async with agent:
            t0 = time.monotonic()
            result = await mesh.call(
                "ground.medevac",
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


async def test_medevac_publishes_status_on_dispatch():
    """At least one MedevacStatus message arrives on mesh.action.medevac.{id}.status."""
    async with AgentMesh.local() as mesh:
        agent = medevac.MedevacAgent(mesh)
        agent.register_handler(
            mesh,
            name="ground.medevac",
            description="Ground medevac.",
        )

        observed_states: list[str] = []
        observed_payloads: list[dict] = []
        first_msg = asyncio.Event()

        async def _on_status(msg) -> None:
            payload = json.loads(msg.data.decode())
            observed_states.append(payload["state"])
            observed_payloads.append(payload)
            first_msg.set()

        sub = await mesh._nc.subscribe(
            f"mesh.action.medevac.{mesh.instance_id}.status",
            cb=_on_status,
        )

        async with agent:
            try:
                ack = await mesh.call(
                    "ground.medevac",
                    _make_order(Coords(x=0.5, y=0.5)),
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
        # Status payload shape: capacity_used + capacity_max present.
        for payload in observed_payloads:
            assert "capacity_used" in payload
            assert "capacity_max" in payload
            assert payload["capacity_max"] == 4


async def test_medevac_rejects_when_over_capacity():
    """persons_estimated + capacity_used > capacity_max -> reason="capacity"."""
    async with AgentMesh.local() as mesh:
        agent = medevac.MedevacAgent(mesh)
        agent.register_handler(
            mesh,
            name="ground.medevac",
            description="Ground medevac.",
        )
        # Pre-charge capacity so the dispatch overflows. capacity_max default 4.
        agent._capacity_used = 3
        async with agent:
            ack = await mesh.call(
                "ground.medevac",
                _make_order(Coords(x=1.0, y=1.0), persons=2),
                timeout=1.0,
            )
            assert ack["accepted"] is False
            assert ack["reason"] == "capacity"
            # Capacity rejection MUST come before the busy check; instance_id
            # is still reported so the operator knows which unit declined.
            assert ack["instance_id"] == mesh.instance_id


async def test_medevac_rejects_concurrent_dispatch_with_busy():
    """A second dispatch while busy returns reason="busy" (inherited base behaviour)."""
    async with AgentMesh.local() as mesh:
        agent = medevac.MedevacAgent(mesh)
        agent.register_handler(
            mesh,
            name="ground.medevac",
            description="Ground medevac.",
        )
        async with agent:
            ack1 = await mesh.call(
                "ground.medevac",
                _make_order(Coords(x=1.0, y=1.0), order_id="o-1"),
                timeout=1.0,
            )
            assert ack1["accepted"] is True
            # Second dispatch while the first simulation is in flight.
            ack2 = await mesh.call(
                "ground.medevac",
                _make_order(Coords(x=2.0, y=2.0), order_id="o-2"),
                timeout=1.0,
            )
            assert ack2["accepted"] is False
            assert ack2["reason"] == "busy"
