"""Phase 1 hardcoded configuration constants for the wildfire demo.

Single source of truth for HQ coords, fleet sizes, heartbeat cadence, and
the fire-sim / UAV / drone tunables. Every fleet member, the orchestrator,
and the spawn CLI imports from here so this file is the dial — there are
no hardcoded magic numbers in the agent modules.

Sources:

- ``.planning/phases/01-detection-foundation/01-CONTEXT.md`` decisions
  D-08 (heli/ffunit boot+heartbeat only), D-09 (1 Hz uniform heartbeat),
  D-10 (3 s reader-side liveness staleness), D-11 (HQ at origin),
  A-03 (200 m world grid, ambient = absent key), A-08 (KV namespaces).
- ``km/specs/wildfire/fire-sim.md`` — FIRE_SIM tick interval, ambient /
  spread / decay tunables, material-change write threshold.
- ``km/specs/wildfire/uav.md`` — UAV sensor footprint, threshold,
  confidence floor, dedup grid + window.
- ``km/specs/wildfire/drone.md`` — drone speed and survey duration.
"""

from __future__ import annotations

from demos.wildfire.core.contracts import Coords

# ---------------------------------------------------------------------------
# HQ + boot
# ---------------------------------------------------------------------------

# Single hardcoded HQ coord (D-11). Helis, ffunits, and the UAV stay here in
# Phase 1; drones depart for surveys and return.
HQ: Coords = Coords(x=0.0, y=0.0)

# ---------------------------------------------------------------------------
# Fleet sizes (D-08; can bump HELI_COUNT to 2 if narrative requires it)
# ---------------------------------------------------------------------------

UAV_COUNT: int = 1
DRONE_COUNT: int = 5
HELI_COUNT: int = 1
FFUNIT_COUNT: int = 3

# ---------------------------------------------------------------------------
# Heartbeat (D-09 + D-10)
# ---------------------------------------------------------------------------

# Every fleet member writes its FleetMemberState to wildfire.fleet.{zone}.{type}.{id}
# at this cadence. Uniform across uav / drone / heli / ffunit.
HEARTBEAT_INTERVAL_S: float = 1.0

# Reader-side staleness cutoff (D-10): an instance is "live" iff
# now - last_updated < this. The admin UI is the canonical reader; this
# constant lets Python-side checks mirror the same logic.
LIVENESS_STALENESS_S: float = 3.0

# ---------------------------------------------------------------------------
# Fire-sim tunables (km/specs/wildfire/fire-sim.md "Behaviour notes")
# ---------------------------------------------------------------------------

# 1 Hz spread tick.
FIRE_SIM_TICK_INTERVAL_S: float = 1.0

# Cells decaying back to this temperature are deleted from KV (sparse grid;
# ambient = absence of a key per A-03).
FIRE_SIM_AMBIENT_C: float = 25.0

# Saturation cap for any single cell.
FIRE_SIM_MAX_C: float = 800.0

# Material-change threshold: fire-sim only writes a cell to KV if its
# temperature shifted by at least this much since the last write. Avoids
# noisy 0.01 C deltas pumping the KV bus.
FIRE_SIM_MATERIAL_DELTA_C: float = 5.0

# Per-tick decay applied to cells that received no input this tick.
FIRE_SIM_DECAY_PER_TICK_C: float = 4.0

# Toy CA spread coefficient: fraction of the (neighbour - cell) delta that
# diffuses into a cell each tick. Tuned later when the demo runs.
FIRE_SIM_SPREAD_DIFFUSION: float = 0.10

# ---------------------------------------------------------------------------
# UAV sensor model (km/specs/wildfire/uav.md)
# ---------------------------------------------------------------------------

# Single static observer at HQ; footprint covers the whole 10 km map for v1.
UAV_FOOTPRINT_RADIUS_KM: float = 5.0

# Cells at or above this temperature are detection candidates.
UAV_TEMP_THRESHOLD_C: float = 100.0

# Detections below this synthesised confidence are dropped.
UAV_CONFIDENCE_FLOOR: float = 0.5

# Dedup hash bucket: 100 m * 30 s. UAV uses ``mesh.kv.create`` (put-if-absent)
# on a key derived from these so duplicate detections from the same hot zone
# within the window collide harmlessly.
UAV_DEDUP_GRID_KM: float = 0.1
UAV_DEDUP_WINDOW_S: float = 30.0

# ---------------------------------------------------------------------------
# Drone (km/specs/wildfire/drone.md)
# ---------------------------------------------------------------------------

# Travel speed. 5 km radius => ~12.5 s to traverse worst case.
DRONE_SPEED_KM_S: float = 0.4

# Time spent on-site once arrived; simulated, no real sensor.
DRONE_SURVEY_DURATION_S: float = 5.0
