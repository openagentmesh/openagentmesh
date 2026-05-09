"""Unit tests for the low-altitude heli agent (SCN-05, SCN-13, D-08).

Phase 1 heli is boot + register + heartbeat ONLY (D-08). The
``DispatchOrder -> DispatchAck`` Responder handler exists for catalog
correctness (so the admin UI sandbox in Phase 3 can introspect the contract)
but is never called this phase. This unit test file is the TDD RED -> GREEN
gate for plan 01-07.

Asserted invariants:

  - Module exposes ``build_agent(mesh)`` and async ``_main()``
  - Source text registers ``AgentSpec(name="low-alt.heli", ...)``
  - Source text uses the shared ``heartbeat_loop`` helper
  - Source text contains zero references to outbound pubsub or KV-source
    plumbing (no ``mesh.publish`` / ``subject_source`` / ``kv_source`` --
    Phase 1 = boot + heartbeat only per D-08)
  - Stub handler returns ``DispatchAck(accepted=False, ...)`` -- if a Phase 2
    caller ever exists before the real body lands, the stub fails loud.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

heli = pytest.importorskip(
    "demos.wildfire.fleet.heli",
    reason="demos.wildfire.fleet.heli not yet on disk (plan 01-07 creates it).",
)


# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_build_agent_is_callable():
    assert callable(heli.build_agent)


def test_main_is_async_coroutine_function():
    assert inspect.iscoroutinefunction(heli._main)


# ---------------------------------------------------------------------------
# Source-text invariants (Phase 1 boot + heartbeat only, per D-08)
# ---------------------------------------------------------------------------


_HELI_PATH = Path(heli.__file__)


def test_heli_module_registers_low_alt_heli_agent_spec():
    text = _HELI_PATH.read_text()
    assert "AgentSpec(" in text
    assert 'name="low-alt.heli"' in text


def test_heli_module_uses_heartbeat_loop_helper():
    text = _HELI_PATH.read_text()
    assert "heartbeat_loop" in text


def test_heli_module_heartbeat_uses_low_alt_heli_zone_and_type():
    text = _HELI_PATH.read_text()
    assert 'zone="low-alt"' in text
    assert 'fleet_type="heli"' in text


@pytest.mark.parametrize(
    "needle",
    [
        "mesh.publish",
        "subject_source",
        "kv_source",
        "ThermalGrid",
        "FireSpawn",
        "FireSuppress",
        "mesh.environment.thermal",
    ],
)
def test_heli_module_does_not_reference_phase2_or_dropped_artefacts(needle: str):
    text = _HELI_PATH.read_text()
    assert needle not in text, (
        f"{needle!r} should not appear in {_HELI_PATH.name} "
        "(Phase 1 = boot + heartbeat only per D-08; pubsub artefacts dropped per A-05/A-08)"
    )


@pytest.mark.parametrize("needle", ["bucket=", "prefix=", "model="])
def test_heli_module_does_not_use_aspirational_kwargs(needle: str):
    # A-09: real SDK has no bucket=/prefix=/model= kwargs on KV / source calls.
    text = _HELI_PATH.read_text()
    assert needle not in text, f"{needle!r} is not a real SDK kwarg (A-09)"


# ---------------------------------------------------------------------------
# Stub-handler shape (catalog correctness; never called Phase 1, D-08)
# ---------------------------------------------------------------------------


def test_heli_stub_handler_returns_unaccepted_dispatch_ack():
    """If a rogue Phase 2 caller ever invokes the Phase 1 stub, the
    response must be a structured ``DispatchAck(accepted=False, ...)`` so
    the failure surfaces loud instead of looking like a silent success.
    """
    text = _HELI_PATH.read_text()
    assert "DispatchAck(" in text
    assert "accepted=False" in text
    assert "phase 1 stub" in text.lower()


# ---------------------------------------------------------------------------
# Live boot test against AgentMesh.local() (D-08, D-20, plan 01-10)
# ---------------------------------------------------------------------------
#
# Boots an embedded NATS, registers the heli agent, runs the heartbeat loop,
# asserts the catalog entry is visible and a FleetMemberState record is
# written under wildfire.fleet.low-alt.heli.{instance_id}. No mesh.call()
# in Phase 1 (D-08).

import asyncio  # noqa: E402
import time  # noqa: E402

from openagentmesh import AgentMesh  # noqa: E402
from demos.wildfire.core.config import HQ  # noqa: E402
from demos.wildfire.core.contracts import FleetMemberState  # noqa: E402
from demos.wildfire.core.heartbeat import heartbeat_loop  # noqa: E402
from demos.wildfire.core.keys import FLEET_PREFIX  # noqa: E402

# NATS wildcard suffix is REQUIRED on every kv.list call; bare prefixes
# return [] per src/openagentmesh/_context.py:375-405. Heli keys are
# wildfire.fleet.low-alt.heli.{instance_id} (one segment after the
# fleet+type prefix), but `>` is safer and consistent across fleets.
HELI_FLEET_WILDCARD = f"{FLEET_PREFIX}.low-alt.heli.>"


async def test_heli_boots_registers_in_catalog_and_emits_heartbeat():
    """Phase 1 heli scope (D-08): boot + register catalog entry + write
    1 Hz heartbeat. No DispatchOrder caller is exercised this phase.
    """
    async with AgentMesh.local() as mesh:
        heli.build_agent(mesh)
        # _subscribe_pending only runs at __aenter__ and on catalog()/call();
        # call catalog() to bind the responder subscription + populate cache.
        entries = await mesh.catalog()
        names = {e.name for e in entries}
        assert "low-alt.heli" in names, (
            f"low-alt.heli should be in the catalog after build_agent + catalog(); "
            f"saw {names}"
        )

        hb = asyncio.create_task(
            heartbeat_loop(
                mesh,
                zone="low-alt",
                fleet_type="heli",
                get_state=lambda: "free",
                get_coords=lambda: HQ,
                get_assignment=lambda: None,
            )
        )
        try:
            # Wait long enough for at least one heartbeat write
            # (HEARTBEAT_INTERVAL_S = 1 s + jitter buffer).
            await asyncio.sleep(1.6)
            heli_entries = [
                e for e in await mesh.kv.list(HELI_FLEET_WILDCARD) if e.value
            ]
            assert len(heli_entries) >= 1, (
                f"expected >= 1 heli heartbeat record under {HELI_FLEET_WILDCARD}; "
                f"got {len(heli_entries)}"
            )
            rec = FleetMemberState.model_validate_json(heli_entries[0].value)
            assert rec.fleet_type == "heli"
            assert rec.zone == "low-alt"
            assert rec.state == "free"
            assert rec.instance_id == mesh.instance_id
            assert time.time() - rec.last_updated < 2.0
        finally:
            hb.cancel()
            try:
                await hb
            except asyncio.CancelledError:
                pass
