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


# ---------------------------------------------------------------------------
# Phase 2 additions: action-fleet ETA + dashboard tunables
# ---------------------------------------------------------------------------


def test_phase2_constants_importable() -> None:
    """Smoke import: every Phase 2 tunable resolves from the config module."""
    from demos.wildfire.core.config import (  # noqa: F401
        DASHBOARD_PORT,
        FFUNIT_ACTION_DURATION_S,
        FFUNIT_SPEED_KM_S,
        HELI_ACTION_DURATION_S,
        HELI_SPEED_KM_S,
        MEDEVAC_ACTION_DURATION_S,
        MEDEVAC_CAPACITY_MAX,
        MEDEVAC_COUNT,
        MEDEVAC_SPEED_KM_S,
        SPAWN_MAGNITUDE_LARGE,
        SPAWN_MAGNITUDE_MEDIUM,
        SPAWN_MAGNITUDE_SMALL,
    )


def test_speed_ordering_invariant() -> None:
    """HELI > MEDEVAC > FFUNIT (km/specs/wildfire/medevac.md positioning)."""
    from demos.wildfire.core.config import (
        FFUNIT_SPEED_KM_S,
        HELI_SPEED_KM_S,
        MEDEVAC_SPEED_KM_S,
    )

    assert HELI_SPEED_KM_S > MEDEVAC_SPEED_KM_S > FFUNIT_SPEED_KM_S
    assert FFUNIT_SPEED_KM_S > 0.0


def test_magnitude_tiers_ordered() -> None:
    """SMALL < MEDIUM < LARGE (browser cycles through tiers in order)."""
    from demos.wildfire.core.config import (
        SPAWN_MAGNITUDE_LARGE,
        SPAWN_MAGNITUDE_MEDIUM,
        SPAWN_MAGNITUDE_SMALL,
    )

    assert SPAWN_MAGNITUDE_SMALL < SPAWN_MAGNITUDE_MEDIUM < SPAWN_MAGNITUDE_LARGE


def test_magnitudes_within_cellstate_band() -> None:
    """All magnitudes stay inside the CellState expected band [25, 800]."""
    from demos.wildfire.core.config import (
        SPAWN_MAGNITUDE_LARGE,
        SPAWN_MAGNITUDE_MEDIUM,
        SPAWN_MAGNITUDE_SMALL,
    )

    for magnitude in (SPAWN_MAGNITUDE_SMALL, SPAWN_MAGNITUDE_MEDIUM, SPAWN_MAGNITUDE_LARGE):
        assert 25.0 <= magnitude <= 800.0


def test_medevac_count_default_three() -> None:
    """MEDEVAC_COUNT defaults to 3 (per CONTEXT.md fleet inventory)."""
    from demos.wildfire.core.config import MEDEVAC_COUNT

    assert MEDEVAC_COUNT == 3


def test_medevac_capacity_max_matches_contract_default() -> None:
    """Config mirrors MedevacStatus.capacity_max default (4)."""
    from demos.wildfire.core.config import MEDEVAC_CAPACITY_MAX

    assert MEDEVAC_CAPACITY_MAX == 4


def test_action_durations_positive() -> None:
    """Each fleet has a positive on-site action duration."""
    from demos.wildfire.core.config import (
        FFUNIT_ACTION_DURATION_S,
        HELI_ACTION_DURATION_S,
        MEDEVAC_ACTION_DURATION_S,
    )

    assert HELI_ACTION_DURATION_S > 0.0
    assert MEDEVAC_ACTION_DURATION_S > 0.0
    assert FFUNIT_ACTION_DURATION_S > 0.0


def test_dashboard_port_default() -> None:
    """DASHBOARD_PORT defaults to 8081 (D-39)."""
    from demos.wildfire.core.config import DASHBOARD_PORT

    assert DASHBOARD_PORT == 8081
