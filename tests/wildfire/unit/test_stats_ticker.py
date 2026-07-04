"""Unit tests for the stats-ticker reporting agent (no LLM).

Pins the pure "KV snapshot lists in -> SwarmStats out" computation
(``compute_stats``), the defensive raw-entry validation layer
(``validate_entries``: skips tombstones, empty bytes, and malformed
payloads that would make ``mesh.kv.list_models`` raise), and one
integration-lite pass of ``run_tick`` against ``AgentMesh.local()``.

Spec: ``km/specs/wildfire/stats-ticker.md``. Followed literally:
"Active" means ``state != "free"`` for every fleet type, uav included,
and an ``"offline"`` record therefore counts as active.
"""

from __future__ import annotations

import asyncio
import time

from demos.wildfire.core.contracts import (
    Coords,
    DetectionRecord,
    FleetMemberState,
    IncidentState,
)
from demos.wildfire.core.keys import (
    detection_key,
    fleet_key,
    incident_key,
)
from demos.wildfire.fleet.stats_ticker import (
    STATS_SUBJECT,
    compute_stats,
    run_tick,
    validate_entries,
)
from openagentmesh import AgentMesh, KVEntry

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

_ZONE_FOR_TYPE = {
    "uav": "high-alt",
    "drone": "low-alt",
    "heli": "low-alt",
    "ffunit": "ground",
    "medevac": "ground",
}


def _member(
    fleet_type: str, state: str, instance_id: str = "i-1"
) -> FleetMemberState:
    return FleetMemberState(
        instance_id=instance_id,
        zone=_ZONE_FOR_TYPE[fleet_type],
        fleet_type=fleet_type,
        coords=Coords(x=0.0, y=0.0),
        state=state,
        current_assignment=None if state == "free" else "det-1",
        last_updated=time.time(),
    )


def _incident(incident_id: str, *, resolved: bool) -> IncidentState:
    return IncidentState(
        incident_id=incident_id,
        detection_ids=["det-1"],
        last_briefing_at=time.time(),
        briefings=[],
        severity="med",
        resolved=resolved,
        resolved_at=time.time() if resolved else None,
    )


def _detection(detection_id: str) -> DetectionRecord:
    now = time.time()
    return DetectionRecord(
        detection_id=detection_id,
        state="pending",
        coords=Coords(x=1.0, y=1.0),
        severity=0.7,
        detector_instance_id="uav-1",
        created_at=now,
        last_updated=now,
    )


def _entry(key: str, value: bytes, operation: str = "PUT") -> KVEntry[bytes]:
    return KVEntry(key=key, value=value, revision=1, operation=operation)


# ---------------------------------------------------------------------------
# compute_stats: pure computation
# ---------------------------------------------------------------------------


def test_compute_stats_empty_inputs_all_zero() -> None:
    stats = compute_stats([], [], 0, now=1234.5)
    assert stats.timestamp == 1234.5
    assert stats.uavs_active == stats.uavs_total == 0
    assert stats.drones_active == stats.drones_total == 0
    assert stats.helis_active == stats.helis_total == 0
    assert stats.ffunits_active == stats.ffunits_total == 0
    assert stats.medevacs_active == stats.medevacs_total == 0
    assert stats.incidents_open == 0
    assert stats.incidents_resolved == 0
    assert stats.fires_detected_total == 0
    assert stats.persons_recovered_total == 0


def test_compute_stats_mixed_fleet_states() -> None:
    fleet = [
        _member("uav", "busy", "uav-1"),
        _member("drone", "free", "drone-1"),
        _member("drone", "busy", "drone-2"),
        _member("drone", "offline", "drone-3"),
        _member("heli", "free", "heli-1"),
        _member("ffunit", "busy", "ff-1"),
        _member("ffunit", "free", "ff-2"),
        _member("medevac", "free", "med-1"),
    ]
    stats = compute_stats(fleet, [], 0, now=time.time())

    assert (stats.uavs_active, stats.uavs_total) == (1, 1)
    # "offline" is state != "free" -> active per the spec's literal
    # definition (two-way split on "free", not a liveness check).
    assert (stats.drones_active, stats.drones_total) == (2, 3)
    assert (stats.helis_active, stats.helis_total) == (0, 1)
    assert (stats.ffunits_active, stats.ffunits_total) == (1, 2)
    assert (stats.medevacs_active, stats.medevacs_total) == (0, 1)


def test_compute_stats_free_uav_is_not_active() -> None:
    """Spec-literal: a uav record with state "free" counts as NOT active,
    even though the UAV is conceptually always observing."""
    stats = compute_stats([_member("uav", "free", "uav-1")], [], 0, now=0.0)
    assert stats.uavs_total == 1
    assert stats.uavs_active == 0


def test_compute_stats_incident_split() -> None:
    incidents = [
        _incident("inc-1", resolved=False),
        _incident("inc-2", resolved=False),
        _incident("inc-3", resolved=True),
    ]
    stats = compute_stats([], incidents, 0, now=0.0)
    assert stats.incidents_open == 2
    assert stats.incidents_resolved == 1


def test_compute_stats_detection_count_passthrough() -> None:
    stats = compute_stats([], [], 7, now=0.0)
    assert stats.fires_detected_total == 7


def test_compute_stats_persons_recovered_is_zero() -> None:
    """No durable persons-recovered source exists (medevac capacity_used is
    in-memory, resets on drop-off, never lands in KV) -> always 0 for v1."""
    fleet = [_member("medevac", "busy", "med-1")]
    stats = compute_stats(fleet, [_incident("inc-1", resolved=True)], 3, now=0.0)
    assert stats.persons_recovered_total == 0


def test_compute_stats_is_deterministic() -> None:
    fleet = [_member("drone", "busy", "drone-1")]
    incidents = [_incident("inc-1", resolved=False)]
    a = compute_stats(fleet, incidents, 2, now=42.0)
    b = compute_stats(fleet, incidents, 2, now=42.0)
    assert a == b


# ---------------------------------------------------------------------------
# validate_entries: defensive raw-KV filtering
# ---------------------------------------------------------------------------


def test_validate_entries_skips_malformed_and_tombstones() -> None:
    good = _member("drone", "busy", "drone-1")
    entries = [
        _entry("wildfire.fleet.low-alt.drone.drone-1",
               good.model_dump_json().encode()),
        _entry("wildfire.fleet.low-alt.drone.garbage", b"not json at all"),
        _entry("wildfire.fleet.low-alt.drone.stale",
               b'{"instance_id": "x", "schema": "from-another-era"}'),
        _entry("wildfire.fleet.low-alt.drone.tombstone", b""),
        _entry("wildfire.fleet.low-alt.drone.deleted",
               good.model_dump_json().encode(), operation="DELETE"),
    ]
    validated = validate_entries(entries, FleetMemberState)
    assert len(validated) == 1
    assert validated[0].instance_id == "drone-1"


def test_validate_entries_empty_input() -> None:
    assert validate_entries([], FleetMemberState) == []


def test_validate_entries_incident_model() -> None:
    inc = _incident("inc-9", resolved=True)
    entries = [
        _entry(incident_key("inc-9"), inc.model_dump_json().encode()),
        _entry(incident_key("bad"), b"{"),
    ]
    validated = validate_entries(entries, IncidentState)
    assert [i.incident_id for i in validated] == ["inc-9"]
    assert validated[0].resolved is True


# ---------------------------------------------------------------------------
# Integration-lite: run_tick against AgentMesh.local()
# ---------------------------------------------------------------------------


async def test_run_tick_reads_kv_and_publishes() -> None:
    """Seed fleet/incident/detection records (plus one malformed fleet
    payload), run one tick, and verify both the returned SwarmStats and
    the frame published on mesh.swarm.stats."""
    async with AgentMesh.local() as mesh:
        await mesh.kv.put_model(
            fleet_key("high-alt", "uav", "uav-1"), _member("uav", "busy", "uav-1")
        )
        await mesh.kv.put_model(
            fleet_key("low-alt", "drone", "drone-1"),
            _member("drone", "free", "drone-1"),
        )
        # Malformed fleet record: must be skipped, not crash the tick.
        await mesh.kv.put(fleet_key("ground", "ffunit", "bad-1"), b"not json")
        await mesh.kv.put_model(incident_key("inc-1"), _incident("inc-1", resolved=False))
        await mesh.kv.put_model(detection_key("det-1"), _detection("det-1"))

        received: list[dict] = []

        async def _capture() -> None:
            async for msg in mesh.subscribe(subject=STATS_SUBJECT, timeout=10.0):
                received.append(msg)
                break

        capture_task = asyncio.create_task(_capture())
        await asyncio.sleep(0.3)  # let the subscription bind

        stats = await run_tick(mesh)

        assert stats is not None
        assert (stats.uavs_active, stats.uavs_total) == (1, 1)
        assert (stats.drones_active, stats.drones_total) == (0, 1)
        assert stats.ffunits_total == 0  # malformed entry skipped
        assert stats.incidents_open == 1
        assert stats.incidents_resolved == 0
        assert stats.fires_detected_total == 1
        assert stats.persons_recovered_total == 0

        await asyncio.wait_for(capture_task, timeout=12.0)
        assert received, "no frame arrived on mesh.swarm.stats"
        assert received[0]["uavs_total"] == 1
        assert received[0]["fires_detected_total"] == 1
