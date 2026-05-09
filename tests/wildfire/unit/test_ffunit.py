"""Unit tests for the ground ffunit agent (SCN-06, SCN-13, D-08).

Phase 1 ffunit is boot + register + heartbeat ONLY (D-08), same shape as
heli (plan 01-07 Task 1). Three orchestrator-spawned instances share the
queue group ``q.ground.ffunit`` automatically per
``src/openagentmesh/_mesh.py:_subscribe_agent`` (FFUNIT_COUNT=3).

Asserted invariants:

  - Module exposes ``build_agent(mesh)`` and async ``_main()``
  - Source text registers ``AgentSpec(name="ground.ffunit", ...)``
  - Source text uses the shared ``heartbeat_loop`` helper with zone="ground",
    fleet_type="ffunit"
  - Source text contains zero references to outbound pubsub or KV-source
    plumbing (no ``mesh.publish`` / ``subject_source`` / ``kv_source`` --
    Phase 1 = boot + heartbeat only per D-08)
  - Stub handler returns ``DispatchAck(accepted=False, ...)`` so a rogue
    Phase 2 caller surfaces loud.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

ffunit = pytest.importorskip(
    "demos.wildfire.fleet.ffunit",
    reason="demos.wildfire.fleet.ffunit not yet on disk (plan 01-07 creates it).",
)


# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_build_agent_is_callable():
    assert callable(ffunit.build_agent)


def test_main_is_async_coroutine_function():
    assert inspect.iscoroutinefunction(ffunit._main)


# ---------------------------------------------------------------------------
# Source-text invariants (Phase 1 boot + heartbeat only, per D-08)
# ---------------------------------------------------------------------------


_FFUNIT_PATH = Path(ffunit.__file__)


def test_ffunit_module_registers_ground_ffunit_agent_spec():
    text = _FFUNIT_PATH.read_text()
    assert "AgentSpec(" in text
    assert 'name="ground.ffunit"' in text


def test_ffunit_module_uses_heartbeat_loop_helper():
    text = _FFUNIT_PATH.read_text()
    assert "heartbeat_loop" in text


def test_ffunit_module_heartbeat_uses_ground_ffunit_zone_and_type():
    text = _FFUNIT_PATH.read_text()
    assert 'zone="ground"' in text
    assert 'fleet_type="ffunit"' in text


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
def test_ffunit_module_does_not_reference_phase2_or_dropped_artefacts(needle: str):
    text = _FFUNIT_PATH.read_text()
    assert needle not in text, (
        f"{needle!r} should not appear in {_FFUNIT_PATH.name} "
        "(Phase 1 = boot + heartbeat only per D-08; pubsub artefacts dropped per A-05/A-08)"
    )


@pytest.mark.parametrize("needle", ["bucket=", "prefix=", "model="])
def test_ffunit_module_does_not_use_aspirational_kwargs(needle: str):
    # A-09: real SDK has no bucket=/prefix=/model= kwargs on KV / source calls.
    text = _FFUNIT_PATH.read_text()
    assert needle not in text, f"{needle!r} is not a real SDK kwarg (A-09)"


# ---------------------------------------------------------------------------
# Stub-handler shape (catalog correctness; never called Phase 1, D-08)
# ---------------------------------------------------------------------------


def test_ffunit_stub_handler_returns_unaccepted_dispatch_ack():
    text = _FFUNIT_PATH.read_text()
    assert "DispatchAck(" in text
    assert "accepted=False" in text
    assert "phase 1 stub" in text.lower()
