"""Canonical KV key + cell-index encoding for the wildfire demo.

Source of truth for:

- The 200 m world-grid cell index encoding (per Amendment A-03 in
  ``.planning/phases/01-detection-foundation/01-CONTEXT.md`` and ADR-0054
  second amendment): ``x_idx = floor((x + 5.0) / 0.2)`` with the ``+5.0``
  edge clamped to index 49 so the grid is 50x50 covering ``[-5, +5]`` km.
- The Phase 1 KV namespaces under the OAM-internal ``mesh-context`` bucket
  (per Amendment A-08, ADR-0054 second amendment): cells live under
  ``wildfire.world.cell.<x_idx>.<y_idx>``, detections under
  ``wildfire.detection.{id}``, fleet liveness under
  ``wildfire.fleet.{zone}.{type}.{instance_id}``.

This module is the single source of truth for those encodings. Every
downstream component that touches the world grid or the per-fleet liveness
namespace (spawn CLI, fire-sim, UAV, drones, helis, ffunits) must import
from here so a future grid-resolution or namespace tweak is a one-file
change.

Pure helpers: no SDK imports, no I/O.
"""

from __future__ import annotations

from demos.wildfire.core.contracts import Coords

# ---------------------------------------------------------------------------
# Namespace prefixes (under the single OAM-internal `mesh-context` bucket)
# ---------------------------------------------------------------------------

WILDFIRE_PREFIX = "wildfire"
CELL_PREFIX = "wildfire.world.cell"
DETECTION_PREFIX = "wildfire.detection"
FLEET_PREFIX = "wildfire.fleet"

# ---------------------------------------------------------------------------
# Grid geometry
# ---------------------------------------------------------------------------

# 200 m per cell, 50x50 grid covering the [-5, +5] km coord box (10 km square).
CELL_SIZE_KM: float = 0.2
GRID_DIM: int = 50


# ---------------------------------------------------------------------------
# Cell index encoding / decoding
# ---------------------------------------------------------------------------


def cell_indices(x: float, y: float) -> tuple[int, int]:
    """Snap a world coordinate to its (x_idx, y_idx) cell index.

    Uses ``int((coord + 5.0) / CELL_SIZE_KM)`` (truncation toward zero for
    non-negative values). Two defensive clamps:

    - The ``+5.0`` edge would otherwise hit index 50; clamp to ``GRID_DIM - 1``
      (49) per A-03.
    - Inputs that round below zero (e.g. due to float artefacts at the
      ``-5.0`` boundary) are clamped to 0.

    Caller is expected to have validated the input via the ``Coords`` model
    (range ``[-5, +5]``); this function does not raise on out-of-range input,
    it clamps.
    """
    x_idx = int((x + 5.0) / CELL_SIZE_KM)
    y_idx = int((y + 5.0) / CELL_SIZE_KM)
    if x_idx < 0:
        x_idx = 0
    elif x_idx >= GRID_DIM:
        x_idx = GRID_DIM - 1
    if y_idx < 0:
        y_idx = 0
    elif y_idx >= GRID_DIM:
        y_idx = GRID_DIM - 1
    return x_idx, y_idx


def cell_center(x_idx: int, y_idx: int) -> Coords:
    """Inverse of :func:`cell_indices`: return the center of cell ``(x_idx, y_idx)``.

    The spawn CLI uses this to write ``CellState.coords`` snapped to the
    canonical 200 m grid (rather than echoing the operator's raw click point).
    """
    cx = -5.0 + (x_idx + 0.5) * CELL_SIZE_KM
    cy = -5.0 + (y_idx + 0.5) * CELL_SIZE_KM
    return Coords(x=cx, y=cy)


# ---------------------------------------------------------------------------
# Key formatting
# ---------------------------------------------------------------------------


def cell_key(x: float, y: float) -> str:
    """Return the KV key for the cell containing world coords ``(x, y)``.

    Format: ``wildfire.world.cell.<x_idx>.<y_idx>`` (per A-08, ADR-0054
    second amendment).
    """
    x_idx, y_idx = cell_indices(x, y)
    return f"{CELL_PREFIX}.{x_idx}.{y_idx}"


def fleet_key(zone: str, fleet_type: str, instance_id: str) -> str:
    """Return the KV key for a fleet-member liveness record.

    Format: ``wildfire.fleet.{zone}.{type}.{instance_id}`` (per D-09 + A-08).
    """
    return f"{FLEET_PREFIX}.{zone}.{fleet_type}.{instance_id}"


def detection_key(detection_id: str) -> str:
    """Return the KV key for a detection record.

    Format: ``wildfire.detection.{detection_id}`` (per A-08).
    """
    return f"{DETECTION_PREFIX}.{detection_id}"
