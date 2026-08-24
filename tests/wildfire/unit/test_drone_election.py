"""Unit tests for the low-altitude drone election logic (SCN-04, A-08, A-09).

Covers the pure-function helpers + module-shape grep gates for the
``low-alt.drone`` agent created by plan 01-06. Per the plan's
``<verify>`` block:

  - ``_distance_km(Coords, Coords)`` is exact euclidean distance in km
  - ``_interpolated(state, now)`` linear-interpolates between travel
    src + dst, clamped to dst once elapsed >= duration
  - module exposes ``DroneState``, ``build_agent``, ``_main`` symbols
  - module references ``mesh.kv.try_cas`` at least twice (claim + complete)
  - exactly one ``mesh.publish`` call (mesh.survey.{instance_id} per A-08)
  - peer-scan ``mesh.kv.list`` carries the NATS wildcard suffix ``.>``
    (a bare prefix returns ``[]`` per ``_context.py`` line 375-405)
  - aspirational kwargs ``bucket=``, ``prefix=``, ``model=`` absent (A-09)
  - ``queue_group`` absent (kv_source raises NotImplementedError on it)
  - dropped Phase-0 pubsub artefacts not referenced (ThermalGrid, FireSpawn,
    FireSuppress, mesh.environment.thermal, subject_source for detections)

Plan 01-09 lays down the handler-level integration tests against
``AgentMesh.local()``; this file is the TDD RED -> GREEN gate for plan
01-06.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

drone = pytest.importorskip(
    "demos.wildfire.fleet.drone",
    reason="demos.wildfire.fleet.drone not yet on disk (plan 01-06 creates it).",
)

from demos.wildfire.core.contracts import Coords  # noqa: E402

# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_build_agent_is_callable():
    assert callable(drone.build_agent)


def test_main_is_async_coroutine_function():
    assert inspect.iscoroutinefunction(drone._main)


def test_drone_state_dataclass_fields():
    state = drone.DroneState(
        current_coords=Coords(x=0.0, y=0.0),
        fleet_state="free",
        assignment_id=None,
    )
    assert state.fleet_state == "free"
    assert state.assignment_id is None
    assert state.current_coords.x == 0.0


# ---------------------------------------------------------------------------
# Distance
# ---------------------------------------------------------------------------


def test_distance_km_3_4_5_triangle():
    assert drone._distance_km(Coords(x=0.0, y=0.0), Coords(x=3.0, y=4.0)) == 5.0


def test_distance_km_zero_when_identical():
    assert drone._distance_km(Coords(x=1.0, y=2.0), Coords(x=1.0, y=2.0)) == 0.0


def test_distance_km_symmetric():
    a = Coords(x=-1.0, y=2.0)
    b = Coords(x=2.0, y=-2.0)
    assert drone._distance_km(a, b) == drone._distance_km(b, a)


# ---------------------------------------------------------------------------
# Travel-time interpolator
# ---------------------------------------------------------------------------


def test_interpolated_returns_current_when_not_travelling():
    s = drone.DroneState(
        current_coords=Coords(x=1.5, y=-2.0),
        fleet_state="free",
        assignment_id=None,
    )
    s.travel_duration = 0.0
    assert drone._interpolated(s, now=100.0) == Coords(x=1.5, y=-2.0)


def test_interpolated_midpoint_at_half_duration():
    s = drone.DroneState(
        current_coords=Coords(x=0.0, y=0.0),
        fleet_state="busy",
        assignment_id="d1",
    )
    s.travel_start = 0.0
    s.travel_duration = 10.0
    s.travel_src = Coords(x=0.0, y=0.0)
    s.travel_dst = Coords(x=4.0, y=0.0)
    mid = drone._interpolated(s, now=5.0)
    assert mid.x == pytest.approx(2.0)
    assert mid.y == pytest.approx(0.0)


def test_interpolated_clamps_to_dst_after_duration():
    s = drone.DroneState(
        current_coords=Coords(x=0.0, y=0.0),
        fleet_state="busy",
        assignment_id="d1",
    )
    s.travel_start = 0.0
    s.travel_duration = 5.0
    s.travel_src = Coords(x=0.0, y=0.0)
    s.travel_dst = Coords(x=2.0, y=2.0)
    out = drone._interpolated(s, now=999.0)
    assert out == Coords(x=2.0, y=2.0)


# ---------------------------------------------------------------------------
# Module text gates (A-05 dropped pubsub artefacts, A-09 real SDK signatures)
# ---------------------------------------------------------------------------


_DRONE_PATH = Path(drone.__file__)
_DRONE_TEXT = _DRONE_PATH.read_text()


@pytest.mark.parametrize(
    "needle",
    [
        "ThermalGrid",
        "FireSpawn",
        "FireSuppress",
        "mesh.environment.thermal",
    ],
)
def test_drone_module_does_not_reference_dropped_pubsub_artefacts(needle: str):
    assert needle not in _DRONE_TEXT, (
        f"{needle!r} should not appear in {_DRONE_PATH.name} (A-04..A-08 dropped it)"
    )


@pytest.mark.parametrize("needle", ["bucket=", "prefix=", "model="])
def test_drone_module_does_not_use_aspirational_kwargs(needle: str):
    # A-09: the real SDK has no bucket=/prefix=/model= kwargs on kv_source/kv calls.
    assert needle not in _DRONE_TEXT, f"{needle!r} is not a real SDK kwarg (A-09)"


def test_drone_module_does_not_pass_queue_group_to_kv_source():
    # kv_source raises NotImplementedError on queue_group= per src/openagentmesh/_mesh.py.
    assert "queue_group" not in _DRONE_TEXT, (
        "kv_source rejects queue_group in v1; the agent must not set it."
    )


def test_drone_module_uses_kv_source_on_detections():
    assert "kv_source" in _DRONE_TEXT
    assert "wildfire.detection" in _DRONE_TEXT


def test_drone_module_uses_try_cas_at_least_twice():
    # claim (pending -> assigned) AND complete (assigned -> surveyed)
    matches = re.findall(r"\btry_cas\b", _DRONE_TEXT)
    assert len(matches) >= 2, (
        f"Expected >= 2 try_cas references (claim + complete); found {len(matches)}"
    )


def test_drone_module_uses_heartbeat_loop_helper():
    assert "heartbeat_loop" in _DRONE_TEXT


def test_drone_module_publishes_exactly_once_on_mesh_survey():
    # A-08: the only Phase 1 pubsub from a drone is mesh.survey.{instance_id}.
    publish_calls = re.findall(r"mesh\.publish\s*\(", _DRONE_TEXT)
    assert len(publish_calls) == 1, (
        f"Expected exactly one mesh.publish call (mesh.survey.{{instance_id}}); "
        f"found {len(publish_calls)}"
    )
    assert re.search(r'mesh\.publish\([^)]*mesh\.survey', _DRONE_TEXT), (
        "The single mesh.publish call must target mesh.survey.{instance_id} (A-08)."
    )


def test_drone_module_peer_scan_uses_nats_wildcard_suffix():
    # mesh.kv.list interprets its argument as a NATS subject; a bare prefix
    # like "wildfire.fleet.low-alt.drone" returns [] (see
    # tests/test_kv_ergonomics.py:31 and src/openagentmesh/_context.py:375-405).
    # The peer scan MUST end with `.>` (or `.*`) so any instance_id matches.
    peer_list_pattern = re.compile(
        r'mesh\.kv\.list\([^)]*low-alt\.drone(\.>|\.\*)["\']\s*\)'
    )
    assert peer_list_pattern.search(_DRONE_TEXT), (
        "Peer scan must call mesh.kv.list with a `.>` or `.*` suffix on the "
        "low-alt.drone fleet prefix; bare-prefix calls return [] in the shipped SDK."
    )


def test_drone_module_has_no_bare_prefix_kv_list_calls():
    # Strip comment-only lines, then assert every mesh.kv.list call ends with
    # a NATS wildcard segment (`.>` or `.*` immediately before the closing
    # quote).
    code_lines = [
        line for line in _DRONE_TEXT.splitlines() if not line.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    for m in re.finditer(r'mesh\.kv\.list\(\s*[^)]*?\)', code):
        snippet = m.group(0)
        # Allow either f-string or plain string forms; assert wildcard suffix.
        assert re.search(r'(\.>|\.\*)["\']\s*\)\s*$', snippet), (
            f"bare-prefix mesh.kv.list call detected: {snippet!r}. Add `.>` "
            f"or `.*` so the NATS wildcard matches all keys under the prefix."
        )


# ---------------------------------------------------------------------------
# Live-integration tests against AgentMesh.local() (D-20, plan 01-10)
# ---------------------------------------------------------------------------
#
# Boots an embedded NATS, exercises the CAS-election helpers (_is_closest_free,
# _claim, _complete) against synthetic peer + detection KV state. No
# mesh.kv.list calls are made directly from this file -- peer scans go
# through drone._list_peers, which uses the NATS wildcard suffix `.>` on
# the low-alt.drone fleet prefix (already gated by
# test_drone_module_peer_scan_uses_nats_wildcard_suffix above).

import time  # noqa: E402

from demos.wildfire.core.contracts import (  # noqa: E402
    DetectionRecord,
    FleetMemberState,
    SurveyResult,
)
from demos.wildfire.core.keys import detection_key, fleet_key  # noqa: E402
from openagentmesh import AgentMesh  # noqa: E402


async def test_is_closest_free_with_closer_peer_returns_false():
    """Self at (0, 0). Peer at (0.5, 0.5) is closer to target (1, 1)."""
    async with AgentMesh.local() as mesh:
        await mesh.kv.put_model(
            fleet_key("low-alt", "drone", "peer-close"),
            FleetMemberState(
                instance_id="peer-close",
                zone="low-alt",
                fleet_type="drone",
                coords=Coords(x=0.5, y=0.5),
                state="free",
                current_assignment=None,
                last_updated=time.time(),
            ),
        )
        state = drone.DroneState(
            current_coords=Coords(x=0.0, y=0.0),
            fleet_state="free",
            assignment_id=None,
        )
        target = Coords(x=1.0, y=1.0)
        assert await drone._is_closest_free(mesh, state, target) is False


async def test_is_closest_free_when_no_closer_peer_returns_true():
    """Self at (0, 0). Peer at (4, 4) is farther than self from target (1, 1)."""
    async with AgentMesh.local() as mesh:
        await mesh.kv.put_model(
            fleet_key("low-alt", "drone", "peer-far"),
            FleetMemberState(
                instance_id="peer-far",
                zone="low-alt",
                fleet_type="drone",
                coords=Coords(x=4.0, y=4.0),
                state="free",
                current_assignment=None,
                last_updated=time.time(),
            ),
        )
        state = drone.DroneState(
            current_coords=Coords(x=0.0, y=0.0),
            fleet_state="free",
            assignment_id=None,
        )
        target = Coords(x=1.0, y=1.0)
        assert await drone._is_closest_free(mesh, state, target) is True


async def test_is_closest_free_ignores_busy_peers():
    """A busy peer at the same distance doesn't disqualify self."""
    async with AgentMesh.local() as mesh:
        await mesh.kv.put_model(
            fleet_key("low-alt", "drone", "peer-busy"),
            FleetMemberState(
                instance_id="peer-busy",
                zone="low-alt",
                fleet_type="drone",
                coords=Coords(x=0.5, y=0.5),  # closer to target than self
                state="busy",  # but busy
                current_assignment="d-other",
                last_updated=time.time(),
            ),
        )
        state = drone.DroneState(
            current_coords=Coords(x=0.0, y=0.0),
            fleet_state="free",
            assignment_id=None,
        )
        assert await drone._is_closest_free(mesh, state, Coords(x=1.0, y=1.0)) is True


async def test_claim_succeeds_on_pending_record_and_writes_assigned_state():
    """`_claim` CAS-transitions a pending DetectionRecord to assigned:{instance_id}."""
    async with AgentMesh.local() as mesh:
        await mesh.kv.put_model(
            detection_key("d-claim-1"),
            DetectionRecord(
                detection_id="d-claim-1",
                state="pending",
                coords=Coords(x=0, y=0),
                severity=0.7,
                detector_instance_id="uav-x",
                created_at=time.time(),
                last_updated=time.time(),
            ),
        )
        won = await drone._claim(mesh, "d-claim-1")
        assert won is True
        rec = await mesh.kv.get_model(detection_key("d-claim-1"), DetectionRecord)
        assert rec.state == f"assigned:{mesh.instance_id}"


async def test_claim_bails_on_already_assigned_record():
    """`_claim` returns False without modifying a record already assigned to another drone."""
    async with AgentMesh.local() as mesh:
        await mesh.kv.put_model(
            detection_key("d-claim-2"),
            DetectionRecord(
                detection_id="d-claim-2",
                state="assigned:other-drone",
                coords=Coords(x=0, y=0),
                severity=0.7,
                detector_instance_id="uav-x",
                created_at=time.time(),
                last_updated=time.time(),
            ),
        )
        won = await drone._claim(mesh, "d-claim-2")
        assert won is False
        rec = await mesh.kv.get_model(detection_key("d-claim-2"), DetectionRecord)
        assert rec.state == "assigned:other-drone"  # unchanged


async def test_complete_writes_surveyed_with_payload():
    """`_complete` CAS-transitions an assigned record to `surveyed` and attaches the SurveyResult."""
    async with AgentMesh.local() as mesh:
        await mesh.kv.put_model(
            detection_key("d-complete-1"),
            DetectionRecord(
                detection_id="d-complete-1",
                state=f"assigned:{mesh.instance_id}",
                coords=Coords(x=0, y=0),
                severity=0.7,
                detector_instance_id="uav-x",
                created_at=time.time(),
                last_updated=time.time(),
            ),
        )
        survey = SurveyResult(
            surveyor_instance_id=mesh.instance_id,
            timestamp=time.time(),
            fire_visible=True,
            persons_detected=2,
            structures_visible=1,
            notes="test survey",
        )
        committed = await drone._complete(mesh, "d-complete-1", survey)
        assert committed is True
        rec = await mesh.kv.get_model(detection_key("d-complete-1"), DetectionRecord)
        assert rec.state == "surveyed"
        assert rec.survey is not None
        assert rec.survey.persons_detected == 2
        assert rec.survey.structures_visible == 1
        assert rec.survey.notes == "test survey"
