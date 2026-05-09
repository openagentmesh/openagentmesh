"""Wildfire demo tunables shared across fleet, world, and orchestrator (D-11, D-08).

Plan 01-03 only needs the fleet counts. Plan 01-01 fills in the rest of the
runtime config (HQ coords, sensor thresholds, simulation tunables). When 01-01
merges, this file is appended/overwritten with the fuller surface; the four
constants below MUST stay stable (the orchestrator imports them).
"""

from __future__ import annotations

# Fleet counts (D-08): 1 UAV + 5 drones + 1 heli + 3 ffunits + 1 fire-sim.
UAV_COUNT: int = 1
DRONE_COUNT: int = 5
HELI_COUNT: int = 1
FFUNIT_COUNT: int = 3
