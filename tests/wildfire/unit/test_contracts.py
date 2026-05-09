"""Phase 1 contract behavioural tests.

Mirrors the Behaviour bullets in 01-01-PLAN.md Task 2. These assertions
encode the canonical shape of `demos.wildfire.core.contracts`.
"""

from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError


def test_phase1_contracts_importable() -> None:
    """Every Phase 1 contract + Literal alias is importable from one module."""
    mod = importlib.import_module("demos.wildfire.core.contracts")
    for name in (
        "Coords",
        "CellState",
        "DetectionRecord",
        "SurveyResult",
        "FleetMemberState",
        "DispatchOrder",
        "DispatchAck",
        "HeliStatus",
        "FFUnitStatus",
        "DetectionState",
        "ActionState",
        "FleetMemberState_StateLit",
    ):
        assert hasattr(mod, name), f"missing contract export: {name}"


def test_dropped_contracts_absent() -> None:
    """ThermalGrid/FireSpawn/FireSuppress are gone (per A-07)."""
    mod = importlib.import_module("demos.wildfire.core.contracts")
    for dropped in ("ThermalGrid", "FireSpawn", "FireSuppress"):
        assert not hasattr(mod, dropped), f"{dropped} should not exist"


def test_coords_bounds_enforced() -> None:
    from demos.wildfire.core.contracts import Coords

    Coords(x=0.0, y=0.0)  # ok
    Coords(x=-5.0, y=5.0)  # ok at boundary
    with pytest.raises(ValidationError):
        Coords(x=10.0, y=0.0)
    with pytest.raises(ValidationError):
        Coords(x=0.0, y=-10.0)


def test_cell_state_round_trip() -> None:
    from demos.wildfire.core.contracts import CellState, Coords

    state = CellState(
        coords=Coords(x=0.0, y=0.0),
        temperature=300.0,
        last_modified_at=0.0,
        last_modified_by="abc",
    )
    blob = state.model_dump_json()
    restored = CellState.model_validate_json(blob)
    assert restored == state


def test_detection_record_defaults() -> None:
    from demos.wildfire.core.contracts import Coords, DetectionRecord

    rec = DetectionRecord(
        detection_id="abc",
        state="pending",
        coords=Coords(x=0.0, y=0.0),
        severity=0.5,
        detector_instance_id="uav-1",
        created_at=0.0,
        last_updated=0.0,
    )
    assert rec.survey is None
    assert rec.incident_id is None


def test_detection_record_state_string_fallback() -> None:
    """state typing accepts the 'assigned:{instance_id}' literal form."""
    from demos.wildfire.core.contracts import Coords, DetectionRecord

    rec = DetectionRecord(
        detection_id="abc",
        state="assigned:somehex",
        coords=Coords(x=0.0, y=0.0),
        severity=0.5,
        detector_instance_id="uav-1",
        created_at=0.0,
        last_updated=0.0,
    )
    assert rec.state == "assigned:somehex"


def test_fleet_member_state_validates() -> None:
    from demos.wildfire.core.contracts import Coords, FleetMemberState

    fms = FleetMemberState(
        instance_id="i1",
        zone="low-alt",
        fleet_type="drone",
        coords=Coords(x=0.0, y=0.0),
        state="free",
        last_updated=0.0,
    )
    assert fms.current_assignment is None


def test_fleet_member_state_invalid_zone_rejected() -> None:
    from demos.wildfire.core.contracts import Coords, FleetMemberState

    with pytest.raises(ValidationError):
        FleetMemberState(
            instance_id="i1",
            zone="invalid-zone",  # type: ignore[arg-type]
            fleet_type="drone",
            coords=Coords(x=0.0, y=0.0),
            state="free",
            last_updated=0.0,
        )
