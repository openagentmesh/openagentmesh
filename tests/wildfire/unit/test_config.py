"""Smoke tests for the Phase 1 wildfire demo config constants.

Pin the canonical values so a downstream agent that imports
``demos.wildfire.core.config`` cannot silently regress them.
"""

from __future__ import annotations

from demos.wildfire.core.config import (
    DRONE_COUNT,
    DRONE_SPEED_KM_S,
    DRONE_SURVEY_DURATION_S,
    FFUNIT_COUNT,
    FIRE_SIM_AMBIENT_C,
    FIRE_SIM_DECAY_PER_TICK_C,
    FIRE_SIM_MATERIAL_DELTA_C,
    FIRE_SIM_MAX_C,
    FIRE_SIM_SPREAD_DIFFUSION,
    FIRE_SIM_TICK_INTERVAL_S,
    HEARTBEAT_INTERVAL_S,
    HELI_COUNT,
    HQ,
    LIVENESS_STALENESS_S,
    UAV_CONFIDENCE_FLOOR,
    UAV_COUNT,
    UAV_DEDUP_GRID_KM,
    UAV_DEDUP_WINDOW_S,
    UAV_FOOTPRINT_RADIUS_KM,
    UAV_TEMP_THRESHOLD_C,
)
from demos.wildfire.core.contracts import Coords


def test_hq_at_origin() -> None:
    assert isinstance(HQ, Coords)
    assert HQ.x == 0.0
    assert HQ.y == 0.0


def test_fleet_sizes() -> None:
    assert UAV_COUNT == 1
    assert DRONE_COUNT == 5
    assert HELI_COUNT == 1
    assert FFUNIT_COUNT == 3


def test_heartbeat_cadence() -> None:
    assert HEARTBEAT_INTERVAL_S == 1.0
    assert LIVENESS_STALENESS_S == 3.0


def test_fire_sim_tunables() -> None:
    assert FIRE_SIM_TICK_INTERVAL_S == 1.0
    assert FIRE_SIM_AMBIENT_C == 25.0
    assert FIRE_SIM_MAX_C == 800.0
    assert FIRE_SIM_MATERIAL_DELTA_C == 5.0
    assert FIRE_SIM_DECAY_PER_TICK_C == 4.0
    assert FIRE_SIM_SPREAD_DIFFUSION == 0.10


def test_uav_sensor_tunables() -> None:
    assert UAV_FOOTPRINT_RADIUS_KM == 5.0
    assert UAV_TEMP_THRESHOLD_C == 100.0
    assert UAV_CONFIDENCE_FLOOR == 0.5
    assert UAV_DEDUP_GRID_KM == 0.1
    assert UAV_DEDUP_WINDOW_S == 30.0


def test_drone_tunables() -> None:
    assert DRONE_SPEED_KM_S == 0.4
    assert DRONE_SURVEY_DURATION_S == 5.0
