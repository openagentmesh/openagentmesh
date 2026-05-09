"""Unit tests for the high-altitude UAV agent (SCN-03, A-05, A-08).

Covers the pure-function detection logic that plan 01-10 integration tests
depend on importing directly:

  - `_confidence(temperature_c)` clipping to [0, 1]
  - `_dedup_id(x, y, now)` -- 16 hex chars from sha1, stable inside the
    100 m * 30 s bucket, distinct across time-window or grid boundaries
  - module exposes `build_agent(mesh)` and `_main()`
  - `mesh.environment.thermal` / `subject_source` / `mesh.publish` are NOT
    referenced anywhere in the module (A-05 dropped them)
  - Aspirational kwargs `bucket=` / `prefix=` / `model=` not used (A-09)

Plan 01-09 lays down the full handler-level integration tests against
`AgentMesh.local()`; this file is the TDD RED -> GREEN gate for plan 01-05.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

uav = pytest.importorskip(
    "demos.wildfire.fleet.uav",
    reason="demos.wildfire.fleet.uav not yet on disk (plan 01-05 creates it).",
)


# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_build_agent_is_callable():
    assert callable(uav.build_agent)


def test_main_is_async_coroutine_function():
    assert inspect.iscoroutinefunction(uav._main)


# ---------------------------------------------------------------------------
# Confidence heuristic
# ---------------------------------------------------------------------------


def test_confidence_floor_at_threshold_temperature():
    # At exactly 100 C the heuristic yields 0.0 (floor of the [0, 1] clip).
    assert uav._confidence(100.0) == 0.0


def test_confidence_saturates_at_max_temperature():
    # At 800 C the heuristic saturates to 1.0 (top of the clip).
    assert uav._confidence(800.0) == 1.0


def test_confidence_clipped_below_threshold():
    assert uav._confidence(50.0) == 0.0


def test_confidence_clipped_above_max():
    assert uav._confidence(1500.0) == 1.0


# ---------------------------------------------------------------------------
# Dedup hash (100 m * 30 s buckets)
# ---------------------------------------------------------------------------


def test_dedup_id_is_16_hex_chars():
    h = uav._dedup_id(0.0, 0.0, 0.0)
    assert isinstance(h, str)
    assert len(h) == 16
    int(h, 16)  # raises ValueError if not hex


def test_dedup_id_stable_inside_grid_bucket():
    # 100 m grid bucket: (0.0, 0.0) and (0.05, 0.05) round to the same bucket.
    assert uav._dedup_id(0.0, 0.0, 0.0) == uav._dedup_id(0.05, 0.05, 0.0)


def test_dedup_id_changes_across_time_window():
    # 30 s window: t=0 and t=31 cross the boundary -> different IDs.
    assert uav._dedup_id(0.0, 0.0, 0.0) != uav._dedup_id(0.0, 0.0, 31.0)


def test_dedup_id_changes_across_grid_bucket():
    # 100 m bucket: (0.0, 0.0) vs (0.2, 0.0) are two buckets apart.
    assert uav._dedup_id(0.0, 0.0, 0.0) != uav._dedup_id(0.2, 0.0, 0.0)


def test_dedup_60s_window_yields_two_distinct_ids():
    # Plan verification: 60 s of 1 Hz ticks straddling the 30 s boundary
    # should produce exactly 2 distinct dedup IDs.
    ids = {uav._dedup_id(0.0, 0.0, t) for t in range(0, 60)}
    assert len(ids) == 2


# ---------------------------------------------------------------------------
# Source contract: zero references to dropped pubsub artefacts (A-05, A-09)
# ---------------------------------------------------------------------------


_UAV_PATH = Path(uav.__file__)


@pytest.mark.parametrize(
    "needle",
    [
        "mesh.environment.thermal",
        "subject_source",
        "mesh.publish",
        "ThermalGrid",
        "FireSpawn",
        "FireSuppress",
    ],
)
def test_uav_module_does_not_reference_dropped_pubsub_artefacts(needle: str):
    text = _UAV_PATH.read_text()
    assert needle not in text, f"{needle!r} should not appear in {_UAV_PATH.name} (A-05 dropped it)"


@pytest.mark.parametrize("needle", ["bucket=", "prefix=", "model="])
def test_uav_module_does_not_use_aspirational_kwargs(needle: str):
    # A-09: real SDK has no bucket=/prefix=/model= kwargs on kv_source/kv calls.
    text = _UAV_PATH.read_text()
    assert needle not in text, f"{needle!r} is not a real SDK kwarg (A-09)"


def test_uav_module_uses_kv_source_on_world_cells():
    text = _UAV_PATH.read_text()
    assert "kv_source" in text
    assert "wildfire.world.cell" in text


def test_uav_module_uses_mesh_kv_create_for_detections():
    text = _UAV_PATH.read_text()
    assert "mesh.kv.create" in text
    # Dedup mechanism is KVKeyExists, not put/put_model overwrite.
    assert "KVKeyExists" in text


def test_uav_module_uses_heartbeat_loop_helper():
    text = _UAV_PATH.read_text()
    assert "heartbeat_loop" in text


# ---------------------------------------------------------------------------
# Live-integration tests against AgentMesh.local() (D-20, plan 01-10)
# ---------------------------------------------------------------------------
#
# Boots the embedded NATS, registers the UAV agent, writes synthetic cell
# states, asserts the resulting DetectionRecord state. NATS subject
# wildcards are mandatory on every kv.list call; bare prefixes return [].

import asyncio  # noqa: E402
import time  # noqa: E402

from openagentmesh import AgentMesh  # noqa: E402
from demos.wildfire.core.contracts import CellState, Coords, DetectionRecord  # noqa: E402
from demos.wildfire.core.keys import DETECTION_PREFIX, cell_key  # noqa: E402

# NATS wildcard suffix — bare prefix returns [] per src/openagentmesh/_context.py:375-405.
DETECTION_WILDCARD = f"{DETECTION_PREFIX}.>"


async def test_uav_writes_pending_detection_on_hot_cell():
    """A hot CellState (>UAV_TEMP_THRESHOLD_C, conf > UAV_CONFIDENCE_FLOOR)
    inside the sensor footprint produces a pending DetectionRecord.
    """
    async with AgentMesh.local() as mesh:
        uav.build_agent(mesh)
        # Source binding is deferred until catalog()/call() per
        # _subscribe_pending; trigger it explicitly so the kv_source fires.
        await mesh.catalog()
        await asyncio.sleep(0.5)

        await mesh.kv.put_model(
            cell_key(0.0, 0.0),
            CellState(
                coords=Coords(x=0.0, y=0.0),
                temperature=600.0,
                last_modified_at=time.time(),
                last_modified_by="external",
            ),
        )

        # Poll for arrival.
        entries: list = []
        for _ in range(30):
            await asyncio.sleep(0.1)
            entries = [e for e in await mesh.kv.list(DETECTION_WILDCARD) if e.value]
            if entries:
                break
        assert len(entries) >= 1, (
            f"expected >= 1 detection, got {len(entries)}"
        )
        rec = DetectionRecord.model_validate_json(entries[0].value)
        assert rec.state == "pending"
        assert rec.severity > 0.5
        assert rec.detector_instance_id == mesh.instance_id


async def test_uav_dedup_swallows_duplicate_hot_writes():
    """Three rapid PUTs on the same cell within the dedup window
    (100 m * 30 s) collide on the dedup hash; only one DetectionRecord
    survives via the put-if-absent (mesh.kv.create) collision.
    """
    async with AgentMesh.local() as mesh:
        uav.build_agent(mesh)
        await mesh.catalog()
        await asyncio.sleep(0.5)

        for _ in range(3):
            await mesh.kv.put_model(
                cell_key(0.0, 0.0),
                CellState(
                    coords=Coords(x=0.0, y=0.0),
                    temperature=600.0,
                    last_modified_at=time.time(),
                    last_modified_by="external",
                ),
            )
            await asyncio.sleep(0.1)

        await asyncio.sleep(0.5)
        entries = [e for e in await mesh.kv.list(DETECTION_WILDCARD) if e.value]
        assert len(entries) == 1, (
            f"dedup should have collapsed 3 hot writes to 1 detection, got {len(entries)}"
        )


async def test_uav_below_threshold_no_detection():
    """A cell below ``UAV_TEMP_THRESHOLD_C`` (100 C) does NOT produce a
    detection — the threshold gate short-circuits before kv.create.
    """
    async with AgentMesh.local() as mesh:
        uav.build_agent(mesh)
        await mesh.catalog()
        await asyncio.sleep(0.5)

        await mesh.kv.put_model(
            cell_key(0.0, 0.0),
            CellState(
                coords=Coords(x=0.0, y=0.0),
                temperature=80.0,
                last_modified_at=time.time(),
                last_modified_by="external",
            ),
        )
        await asyncio.sleep(0.5)
        entries = [e for e in await mesh.kv.list(DETECTION_WILDCARD) if e.value]
        assert entries == []


async def test_uav_outside_footprint_no_detection():
    """A hot cell outside the sensor footprint (HQ at origin, 5 km radius)
    does NOT produce a detection — the footprint gate short-circuits.

    The CellState contract clips coords to ``[-5, +5]`` per axis, so a
    truly out-of-footprint cell still has to be inside that box. We pin
    the cell at the boundary corner (4.9, 4.9), distance ~6.93 km from
    HQ — outside the 5 km footprint.
    """
    async with AgentMesh.local() as mesh:
        uav.build_agent(mesh)
        await mesh.catalog()
        await asyncio.sleep(0.5)

        await mesh.kv.put_model(
            cell_key(4.9, 4.9),
            CellState(
                coords=Coords(x=4.9, y=4.9),
                temperature=600.0,
                last_modified_at=time.time(),
                last_modified_by="external",
            ),
        )
        await asyncio.sleep(0.5)
        entries = [e for e in await mesh.kv.list(DETECTION_WILDCARD) if e.value]
        assert entries == [], (
            "cell at (4.9, 4.9) is ~6.93 km from HQ (origin); "
            "outside the 5 km footprint, must NOT produce a detection"
        )
