"""high-alt.uav: kv_source-driven thermal detector (SCN-03, A-05, A-08).

The UAV is a Watcher (no invocable handler): every cell update under
``wildfire.world.cell.*`` fires the source-driven handler, which applies a
sensor footprint + threshold + confidence floor and writes a pending
``DetectionRecord`` via put-if-absent on a dedup hash. Duplicate hash
collisions are silent (the existing record stands).

Per plan 01-05 + A-05:

- The handler binds to ``mesh.kv_source(f"{CELL_PREFIX}.*", on_init="replay")``
  so the boot snapshot of every existing cell re-fires the threshold check
  at agent restart.
- The handler shape is ``async def uav(entry: KVEntry[CellState]) -> None``,
  which lets us gate ``operation == "DELETE"`` without parsing the payload.
- DELETE entries (cells decayed back to ambient or suppressed) are ignored
  per ``km/specs/wildfire/uav.md`` -- detections are not retracted in v1.
- Detection writes use ``mesh.kv.create`` (raises ``KVKeyExists`` on
  collision, ADR-0060). The collision IS the dedup mechanism.
- A 1 Hz heartbeat task (``heartbeat_loop``) keeps the admin UI registry
  seeing this UAV as live.

This module does NOT subscribe to any subject, does NOT publish on any
subject, and does NOT scan KV (no ``mesh.kv.list`` for cells -- the
handler is event-driven per A-05).

UAV count is 1 (D-08); the orchestrator spawns one process running this
module. Catalog name "high-alt.uav" is registered once.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import math
import os
import time

from demos.wildfire.core.config import (
    HQ,
    UAV_CONFIDENCE_FLOOR,
    UAV_DEDUP_GRID_KM,
    UAV_DEDUP_WINDOW_S,
    UAV_FOOTPRINT_RADIUS_KM,
    UAV_TEMP_THRESHOLD_C,
)
from demos.wildfire.core.contracts import CellState, DetectionRecord
from demos.wildfire.core.heartbeat import heartbeat_loop
from demos.wildfire.core.keys import CELL_PREFIX, detection_key
from openagentmesh import AgentMesh
from openagentmesh._context import KVEntry
from openagentmesh._errors import KVKeyExists
from openagentmesh._models import AgentSpec

_log = logging.getLogger("wildfire.uav")


# ---------------------------------------------------------------------------
# Pure helpers (importable by plan 01-10 unit tests)
# ---------------------------------------------------------------------------


def _distance_km(ax: float, ay: float, bx: float, by: float) -> float:
    """Euclidean distance in km between two world coords."""
    return math.hypot(ax - bx, ay - by)


def _confidence(temperature_c: float) -> float:
    """Sensor confidence heuristic: ``(temp - 100) / 700`` clipped to [0, 1].

    100 C floors to 0.0 (the detection threshold). 800 C saturates to 1.0
    (the fire-sim cap, see ``FIRE_SIM_MAX_C``).
    """
    return max(0.0, min(1.0, (temperature_c - 100.0) / 700.0))


def _dedup_id(x: float, y: float, now: float) -> str:
    """Stable detection ID for a (cell area, time window) bucket.

    Per ``km/specs/wildfire/uav.md`` Behaviour notes + 01-CONTEXT "Claude's
    Discretion": bucket coords by ``UAV_DEDUP_GRID_KM`` (= 100 m) and time
    by ``UAV_DEDUP_WINDOW_S`` (= 30 s), then hash the tuple to 16 hex chars.

    Two cells in the same 100 m bucket within the same 30 s window collide
    on the dedup hash; ``mesh.kv.create`` then raises ``KVKeyExists`` and
    the duplicate write is dropped.
    """
    x_b = round(x / UAV_DEDUP_GRID_KM)
    y_b = round(y / UAV_DEDUP_GRID_KM)
    t_b = int(now // UAV_DEDUP_WINDOW_S)
    return hashlib.sha1(f"{x_b}:{y_b}:{t_b}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------


def build_agent(mesh: AgentMesh) -> None:
    """Register the high-alt.uav agent on ``mesh``.

    Idempotent at call time (caller picks the lifecycle); the handler is
    bound but not started until the surrounding ``async with mesh:`` block.
    """

    @mesh.agent(
        AgentSpec(
            name="high-alt.uav",
            description=(
                "High-altitude thermal observer; writes pending detections from "
                "world-cell updates. Use to surface thermal anomalies above the "
                "detection threshold; do NOT use to query historical detections."
            ),
        ),
        # KV-watch source: kv_source("wildfire.world.cell.>") -- expanded
        # literal kept in this comment alongside the f-string call so
        # cross-repo greps locate the subject pattern here too. The
        # canonical constant is demos.wildfire.core.keys.CELL_PREFIX.
        # Cell keys carry two trailing segments (`.<x_idx>.<y_idx>`), so the
        # wildcard MUST be `>` (one or more); `*` matches one segment only
        # and would never fire on real cell writes (see plan 01-10).
        sources=[mesh.kv_source(f"{CELL_PREFIX}.>", on_init="replay")],
    )
    async def uav(entry: KVEntry[CellState]) -> None:
        # DELETE: cell decayed back to ambient or was suppressed. Detections
        # are not retracted in v1 (briefer handles incident closure later).
        if entry.operation == "DELETE":
            return

        cell = entry.value
        try:
            # Sensor footprint: only cells within UAV_FOOTPRINT_RADIUS_KM of HQ.
            if _distance_km(cell.coords.x, cell.coords.y, HQ.x, HQ.y) > UAV_FOOTPRINT_RADIUS_KM:
                return
            # Temperature threshold.
            if cell.temperature <= UAV_TEMP_THRESHOLD_C:
                return
            # Confidence floor.
            conf = _confidence(cell.temperature)
            if conf < UAV_CONFIDENCE_FLOOR:
                return

            now = time.time()
            detection_id = _dedup_id(cell.coords.x, cell.coords.y, now)
            record = DetectionRecord(
                detection_id=detection_id,
                state="pending",
                coords=cell.coords,
                severity=conf,
                detector_instance_id=mesh.instance_id,
                created_at=now,
                last_updated=now,
                survey=None,
                incident_id=None,
            )
            try:
                await mesh.kv.create(detection_key(detection_id), record)
                _log.info(
                    "detected: %s @ (%.2f, %.2f) temp=%.1f conf=%.2f",
                    detection_id,
                    cell.coords.x,
                    cell.coords.y,
                    cell.temperature,
                    conf,
                )
            except KVKeyExists:
                # Dedup: a prior write in the same 100 m * 30 s bucket already
                # created the record. The existing record stands.
                pass
        except Exception as e:
            # One bad cell does not kill the agent.
            _log.warning("uav handler error on key %r: %s", entry.key, e)


# ---------------------------------------------------------------------------
# Process entry point: `python -m demos.wildfire.fleet.uav`
# ---------------------------------------------------------------------------


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    build_agent(mesh)

    async with mesh:
        hb = asyncio.create_task(
            heartbeat_loop(
                mesh,
                zone="high-alt",
                fleet_type="uav",
                get_state=lambda: "free",
                get_coords=lambda: HQ,
                get_assignment=lambda: None,
            )
        )
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            hb.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await hb


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
