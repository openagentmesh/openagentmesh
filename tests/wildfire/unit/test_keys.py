"""Tests for the canonical cell-index encoding and KV namespace helpers.

Pins the behaviour of ``demos.wildfire.core.keys`` so a downstream tweak
to grid resolution or namespace strings does not silently desync the
spawn CLI, fire-sim, and UAV.
"""

from __future__ import annotations

import pytest

from demos.wildfire.core.contracts import Coords
from demos.wildfire.core.keys import (
    CELL_PREFIX,
    CELL_SIZE_KM,
    DETECTION_PREFIX,
    FLEET_PREFIX,
    GRID_DIM,
    WILDFIRE_PREFIX,
    cell_center,
    cell_indices,
    cell_key,
    detection_key,
    fleet_key,
)


def test_namespace_constants() -> None:
    assert WILDFIRE_PREFIX == "wildfire"
    assert CELL_PREFIX == "wildfire.world.cell"
    assert DETECTION_PREFIX == "wildfire.detection"
    assert FLEET_PREFIX == "wildfire.fleet"
    assert CELL_SIZE_KM == 0.2
    assert GRID_DIM == 50


@pytest.mark.parametrize(
    "x,y,expected",
    [
        (5.0, 5.0, (49, 49)),  # +edge clamp per A-03
        (-5.0, -5.0, (0, 0)),  # -edge
        (0.0, 0.0, (25, 25)),  # origin
        (-4.9, -4.9, (0, 0)),  # first cell
        (4.9, 4.9, (49, 49)),  # last cell
        (-0.1, 0.1, (24, 25)),  # straddles origin
    ],
)
def test_cell_indices(x: float, y: float, expected: tuple[int, int]) -> None:
    assert cell_indices(x, y) == expected


def test_cell_key_format() -> None:
    assert cell_key(0.0, 0.0) == "wildfire.world.cell.25.25"
    assert cell_key(5.0, 5.0) == "wildfire.world.cell.49.49"
    assert cell_key(-5.0, -5.0) == "wildfire.world.cell.0.0"


def test_cell_center_round_trip() -> None:
    """cell_center returns a Coords whose cell_indices round-trips."""
    for x_idx, y_idx in [(0, 0), (25, 25), (49, 49), (12, 37)]:
        c = cell_center(x_idx, y_idx)
        assert isinstance(c, Coords)
        assert cell_indices(c.x, c.y) == (x_idx, y_idx)


def test_cell_center_at_origin_cell() -> None:
    c = cell_center(25, 25)
    # cell 25 covers [0, 0.2); center is at 0.1
    assert abs(c.x - 0.1) < 1e-9
    assert abs(c.y - 0.1) < 1e-9


def test_fleet_key_format() -> None:
    assert fleet_key("low-alt", "drone", "abc123") == "wildfire.fleet.low-alt.drone.abc123"
    assert fleet_key("high-alt", "uav", "u-0") == "wildfire.fleet.high-alt.uav.u-0"
    assert fleet_key("ground", "ffunit", "f-2") == "wildfire.fleet.ground.ffunit.f-2"


def test_detection_key_format() -> None:
    assert detection_key("xyz") == "wildfire.detection.xyz"
    assert detection_key("abc-123") == "wildfire.detection.abc-123"
