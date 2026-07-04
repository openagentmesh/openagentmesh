"""stats-ticker: deterministic SwarmStats snapshots every 10 s (no LLM).

Per ``km/specs/wildfire/stats-ticker.md``: an always-on, single-instance
reporting agent that reads the wildfire KV namespaces every
``STATS_TICK_INTERVAL_S`` seconds, computes aggregate counters, and
publishes a ``SwarmStats`` frame on the flat demo subject
``mesh.swarm.stats`` via ``mesh.publish`` (spec open-question resolved to
option #2: flat subject, not a Publisher's auto-mapped event subject).

Shape:

- One ``@mesh.agent`` registration whose handler is the ADR-0042 Watcher
  form (``async def stats_ticker() -> None``, no input, no return). The
  SDK runs the handler as a background task; the body is the tick loop
  (``_tick_loop``), mirroring fire-sim's ``_spread_loop`` convention with
  sleep-first cadence and per-tick defensive error handling.
- The KV-snapshot -> SwarmStats step is a pure function
  (:func:`compute_stats`) so unit tests need no NATS.
- KV reads use ``mesh.kv.list(prefix)`` raw-bytes snapshots plus
  per-entry validation (:func:`validate_entries`) rather than
  ``mesh.kv.list_models``: ``list_models`` raises on the FIRST malformed
  payload (it validates in a list comprehension with no guard), and the
  fleet namespace can carry legacy/stale-schema records across demo
  restarts (see AGENT_NOTES.md "Demo boots are not clean-slate").
  Malformed entries are skipped, never fatal.

Counter definitions (spec "Behaviour notes", followed literally):

- "Active" means ``state != "free"`` in the fleet KV record. This applies
  uniformly to every fleet type, including the UAV: a uav record with
  ``state == "free"`` counts as NOT active even though the UAV is always
  observing.
- "Total" means count of (valid) records under the type.
- ``incidents_open`` counts ``resolved == False``; ``incidents_resolved``
  counts ``resolved == True``.
- ``fires_detected_total`` is the count of live ``wildfire.detection.*``
  keys.
- ``persons_recovered_total`` is 0 for v1: no durable source exists. The
  medevac's ``_capacity_used`` counter is in-memory per instance and
  resets to 0 on drop-off (``demos/wildfire/fleet/medevac.py``); it only
  surfaces transiently on the ``MedevacStatus`` pubsub feed, never in KV.

Reliability: counters are best-effort, not authoritative. A failed KV
read or publish logs a warning and skips the tick; the loop never dies.

Boot UX::

    python -m demos.wildfire.fleet.stats_ticker

Reads ``NATS_URL`` (default ``nats://127.0.0.1:4222``); the orchestrator
in ``demos/wildfire/__main__.py`` exports it for child processes.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import time
from collections.abc import Iterable, Sequence
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from demos.wildfire.core.config import STATS_TICK_INTERVAL_S
from demos.wildfire.core.contracts import (
    FleetMemberState,
    IncidentState,
    SwarmStats,
)
from demos.wildfire.core.keys import (
    DETECTION_PREFIX,
    FLEET_PREFIX,
    INCIDENT_PREFIX,
)
from openagentmesh import AgentMesh, AgentSpec, KVEntry

_log = logging.getLogger("wildfire.stats_ticker")

# Flat demo pubsub subject (spec "Subject + KV contracts").
STATS_SUBJECT = "mesh.swarm.stats"

# Fleet types tracked by SwarmStats, in contract order.
_FLEET_TYPES = ("uav", "drone", "heli", "ffunit", "medevac")

M = TypeVar("M", bound=BaseModel)


# ---------------------------------------------------------------------------
# Pure computation (no SDK, no I/O) -- unit-testable without NATS
# ---------------------------------------------------------------------------


def validate_entries(
    entries: Sequence[KVEntry[bytes]], model_cls: type[M]
) -> list[M]:
    """Validate raw KV snapshot entries to ``model_cls``, skipping bad ones.

    Skips, without raising:

    - DELETE-op entries (tombstones surfaced by the snapshot watcher);
    - empty-bytes values (NATS KV delete markers can surface as PUTs with
      ``b""`` -- a known nats-py quirk, see test_fire_sim.py);
    - payloads that fail model validation (legacy/stale-schema records
      replayed from a persisted JetStream store across demo restarts).
    """
    validated: list[M] = []
    for entry in entries:
        if entry.operation == "DELETE" or not entry.value:
            continue
        try:
            validated.append(model_cls.model_validate_json(entry.value))
        except ValidationError:
            _log.debug("skipping malformed KV entry %r", entry.key)
    return validated


def compute_stats(
    fleet_records: Iterable[FleetMemberState],
    incident_records: Iterable[IncidentState],
    detection_count: int,
    now: float,
) -> SwarmStats:
    """Fold validated KV snapshots into a ``SwarmStats`` frame.

    Deterministic and pure: same inputs, same output. "Active" is
    ``state != "free"`` per the spec, applied literally to every fleet
    type (an ``"offline"`` record therefore counts as active; the spec's
    definition is a two-way split on ``"free"``, not a liveness check).
    """
    totals: dict[str, int] = {t: 0 for t in _FLEET_TYPES}
    actives: dict[str, int] = {t: 0 for t in _FLEET_TYPES}
    for record in fleet_records:
        if record.fleet_type not in totals:  # defensive; Literal-validated
            continue
        totals[record.fleet_type] += 1
        if record.state != "free":
            actives[record.fleet_type] += 1

    incidents_open = 0
    incidents_resolved = 0
    for incident in incident_records:
        if incident.resolved:
            incidents_resolved += 1
        else:
            incidents_open += 1

    return SwarmStats(
        timestamp=now,
        uavs_active=actives["uav"],
        uavs_total=totals["uav"],
        drones_active=actives["drone"],
        drones_total=totals["drone"],
        helis_active=actives["heli"],
        helis_total=totals["heli"],
        ffunits_active=actives["ffunit"],
        ffunits_total=totals["ffunit"],
        medevacs_active=actives["medevac"],
        medevacs_total=totals["medevac"],
        incidents_open=incidents_open,
        incidents_resolved=incidents_resolved,
        fires_detected_total=detection_count,
        # No durable persons-recovered source exists: medevac capacity_used
        # is in-memory per instance, resets on drop-off, and never lands in KV.
        persons_recovered_total=0,
    )


# ---------------------------------------------------------------------------
# One tick: KV snapshots in, publish out (never raises)
# ---------------------------------------------------------------------------


async def run_tick(mesh: AgentMesh) -> SwarmStats | None:
    """Read KV, compute, publish one ``SwarmStats`` frame.

    Returns the published frame, or ``None`` when the tick was skipped
    (KV read or publish failure). Never raises: counters are best-effort
    and the wrapping loop must survive any single bad tick.
    """
    try:
        # Fleet keys have three trailing segments ({zone}.{type}.{id});
        # NATS `*` matches exactly one segment, so the wildcard must be `>`
        # (lesson pinned by fire-sim's plan 01-10 live-integration tests).
        fleet_raw = await mesh.kv.list(f"{FLEET_PREFIX}.>")
        incident_raw = await mesh.kv.list(f"{INCIDENT_PREFIX}.>")
        detection_raw = await mesh.kv.list(f"{DETECTION_PREFIX}.>")
    except Exception as e:
        _log.warning("stats tick skipped: KV read failed: %s", e)
        return None

    fleet_records = validate_entries(fleet_raw, FleetMemberState)
    incident_records = validate_entries(incident_raw, IncidentState)
    # Detections are counted, not validated: a live key is a detection.
    detection_count = sum(
        1 for e in detection_raw if e.operation != "DELETE" and e.value
    )

    stats = compute_stats(
        fleet_records, incident_records, detection_count, time.time()
    )

    try:
        await mesh.publish(STATS_SUBJECT, stats)
    except Exception as e:
        _log.warning("stats tick skipped: publish failed: %s", e)
        return None
    return stats


async def _tick_loop(mesh: AgentMesh) -> None:
    """Emit one stats frame every ``STATS_TICK_INTERVAL_S`` seconds.

    Sleep-first cadence (mirrors fire-sim's ``_spread_loop``): the first
    frame lands one interval after boot, once fleets have heartbeated.
    """
    try:
        while True:
            await asyncio.sleep(STATS_TICK_INTERVAL_S)
            await run_tick(mesh)
    except asyncio.CancelledError:
        return


# ---------------------------------------------------------------------------
# Agent registration + process entry point
# ---------------------------------------------------------------------------


def build_agent(mesh: AgentMesh) -> None:
    """Register the stats-ticker Watcher agent on ``mesh``.

    The handler is the ADR-0042 Watcher shape (no input, no return): the
    SDK runs it as a background task for the lifetime of the mesh and
    cancels it on shutdown. Split out so tests can register against an
    ``AgentMesh.local()`` fixture without the ``__main__`` boot path.
    """

    @mesh.agent(
        AgentSpec(
            name="stats-ticker",
            description=(
                "Deterministic swarm counters: reads wildfire.fleet.*, "
                "wildfire.incident.*, and wildfire.detection.* from KV every "
                f"{STATS_TICK_INTERVAL_S:.0f}s and publishes a SwarmStats "
                "snapshot on mesh.swarm.stats. Read-only reporter; not "
                "invocable, dispatches nothing, and is never authoritative."
            ),
        )
    )
    async def stats_ticker() -> None:
        await _tick_loop(mesh)


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    build_agent(mesh)

    # Wire SIGTERM/SIGINT to a clean-shutdown event so the orchestrator's
    # Popen.terminate() unblocks the wait the same way Ctrl-C does
    # (same pattern as demos/wildfire/world/fire_sim.py).
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop_event.set)

    async with mesh:
        # The SDK runs the Watcher handler (the tick loop) as a background
        # task and cancels it in _shutdown(); nothing else to manage here.
        with contextlib.suppress(asyncio.CancelledError):
            await stop_event.wait()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
