"""low-alt.drone: kv_source CAS-elected surveyor (SCN-04, A-08, A-09).

The drone is a Watcher (no invocable handler): every detection update under
``wildfire.detection.*`` fires the source-driven handler, which runs the
peer-position election protocol (per ``km/specs/wildfire/drone.md``) and,
on win, simulates travel + survey before CAS-transitioning the detection
to ``state="surveyed"`` and publishing a ``mesh.survey.{instance_id}``
event (the only Phase 1 outbound subject from this agent, A-08).

Per plan 01-06 + Amendments A-08 / A-09 in 01-CONTEXT.md:

- Source: ``mesh.kv_source("wildfire.detection.*", on_init="replay")``.
  Replay is harmless because the election re-reads the detection inside
  ``mesh.kv.try_cas`` and stale events bail safely.
- Handler shape: ``async def drone(entry: KVEntry[DetectionRecord]) -> None``.
  ``entry.operation == "DELETE"`` short-circuits the handler.
- Peer scan uses ``mesh.kv.list(f"{FLEET_PREFIX}.low-alt.drone.>")``. The
  trailing ``.>`` is REQUIRED: ``mesh.kv.list`` interprets the argument
  as a NATS subject and a bare prefix returns ``[]`` (see
  ``tests/test_kv_ergonomics.py``:31 and ``src/openagentmesh/_context.py``
  lines 375-405).
- Election bails before ``try_cas`` if the drone is busy, the detection
  is not ``state="pending"``, or any free peer is closer than self.
- CAS-claim writes ``state="assigned:{mesh.instance_id}"``; on race-loss
  ``cas.committed`` is False and the handler returns silently.
- After simulated travel + survey, a second ``mesh.kv.try_cas`` writes
  ``state="surveyed"`` and attaches the ``SurveyResult`` payload, then
  the agent broadcasts the event on ``mesh.survey.{instance_id}`` via
  the SDK publish primitive (A-08).
- A 1 Hz heartbeat task (``heartbeat_loop``) writes ``FleetMemberState``
  to ``wildfire.fleet.low-alt.drone.{instance_id}`` with state
  transitions free -> busy -> free across the survey lifecycle, and
  interpolated coords during travel (D-09, D-10, "Claude's Discretion"
  in 01-CONTEXT.md).

Drone count is 5 (D-08); the orchestrator spawns 5 separate processes
running this module. Each process gets its own ``mesh.instance_id`` and
its own ``low-alt.drone`` registration. NATS queue-group load
balancing is NOT used: ``kv_source`` rejects that kwarg in v1 (see
``src/openagentmesh/_mesh.py``); the CAS resolves the race instead.

Boot-window note: until each drone has emitted at least one heartbeat,
``_list_peers`` returns an incomplete peer set. This is benign because
the CAS on the detection record (not the peer scan) is the race resolver.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import time
from dataclasses import dataclass, field

from demos.wildfire.core.chaos import chaos_kill_listener
from demos.wildfire.core.config import (
    DRONE_SPEED_KM_S,
    DRONE_SURVEY_DURATION_S,
    HQ,
)
from demos.wildfire.core.contracts import (
    Coords,
    DetectionRecord,
    FleetMemberState,
    FleetMemberState_StateLit,
    SurveyResult,
)
from demos.wildfire.core.heartbeat import heartbeat_loop
from demos.wildfire.core.keys import (
    DETECTION_PREFIX,
    FLEET_PREFIX,
    detection_key,
)
from openagentmesh import AgentMesh
from openagentmesh._context import KVEntry
from openagentmesh._models import AgentSpec

_log = logging.getLogger("wildfire.drone")


# ---------------------------------------------------------------------------
# Per-process state
# ---------------------------------------------------------------------------


@dataclass
class DroneState:
    """Mutable per-process state shared across the handler, the heartbeat
    loop, and the position interpolator.

    The heartbeat coroutine in ``demos.wildfire.core.heartbeat`` reads
    ``current_coords`` and ``fleet_state`` via lambdas, so updates here
    show up in the next 1 Hz tick without explicit signalling.
    """

    current_coords: Coords
    fleet_state: FleetMemberState_StateLit
    assignment_id: str | None
    # Linear-travel interpolation parameters (set by the handler when a
    # survey starts; the interpolator task reads them at 4 Hz).
    travel_start: float = 0.0
    travel_duration: float = 0.0
    travel_src: Coords = field(default_factory=lambda: HQ)
    travel_dst: Coords = field(default_factory=lambda: HQ)


# ---------------------------------------------------------------------------
# Pure helpers (importable by plan 01-09 / 01-10 unit tests)
# ---------------------------------------------------------------------------


def _distance_km(a: Coords, b: Coords) -> float:
    """Euclidean distance in km between two world coordinates."""
    return math.hypot(a.x - b.x, a.y - b.y)


def _interpolated(state: DroneState, now: float) -> Coords:
    """Linear interpolation between ``travel_src`` and ``travel_dst``.

    Returns ``current_coords`` when no travel is active
    (``travel_duration <= 0``). Once ``elapsed >= travel_duration``,
    snaps to ``travel_dst`` so the heartbeat does not stutter past the
    target.
    """
    if state.travel_duration <= 0:
        return state.current_coords
    elapsed = now - state.travel_start
    if elapsed >= state.travel_duration:
        return state.travel_dst
    f = max(0.0, elapsed / state.travel_duration)
    return Coords(
        x=state.travel_src.x + f * (state.travel_dst.x - state.travel_src.x),
        y=state.travel_src.y + f * (state.travel_dst.y - state.travel_src.y),
    )


async def _interpolator(state: DroneState) -> None:
    """Update ``state.current_coords`` at 4 Hz so the 1 Hz heartbeat
    sees a smooth track between source and target during travel."""
    try:
        while True:
            state.current_coords = _interpolated(state, time.time())
            await asyncio.sleep(0.25)
    except asyncio.CancelledError:
        return


# ---------------------------------------------------------------------------
# KV reads (peer scan)
# ---------------------------------------------------------------------------


async def _list_peers(mesh: AgentMesh) -> list[FleetMemberState]:
    """Return current ``FleetMemberState`` records for every low-alt drone.

    The trailing ``.>`` is REQUIRED. ``mesh.kv.list`` interprets the
    argument as a NATS subject (see ``_context.py`` lines 375-405); a
    bare prefix like ``"wildfire.fleet.low-alt.drone"`` is treated as an
    exact key and returns ``[]``. ``>`` matches one-or-more segments so
    any ``instance_id`` shape (uuid hex, dotted) lands in the scan.
    """
    entries = await mesh.kv.list(f"{FLEET_PREFIX}.low-alt.drone.>")
    out: list[FleetMemberState] = []
    for e in entries:
        try:
            out.append(FleetMemberState.model_validate_json(e.value))
        except Exception:
            # Bad shapes are silently dropped (T-01-06-01: Phase 1 trusts
            # every writer; a malformed payload from a peer is not a panic).
            continue
    return out


async def _is_closest_free(
    mesh: AgentMesh, state: DroneState, target: Coords,
) -> bool:
    """Return True iff no free peer is strictly closer than self.

    ``state.current_coords`` is read once at call time (not inside the
    CAS); the boot-window staleness this introduces is benign because
    the CAS on the detection record is the race resolver.
    """
    peers = await _list_peers(mesh)
    my_distance = _distance_km(state.current_coords, target)
    for p in peers:
        if p.instance_id == mesh.instance_id:
            continue
        if p.state != "free":
            continue
        if _distance_km(p.coords, target) < my_distance:
            return False
    return True


# ---------------------------------------------------------------------------
# CAS-election helpers
# ---------------------------------------------------------------------------


async def _claim(mesh: AgentMesh, detection_id: str) -> bool:
    """Try to transition the detection record from ``pending`` to
    ``assigned:{my_instance_id}``.

    Returns True iff this drone won the CAS race. On any read error or
    a non-pending state the function returns False without writing.
    """
    async with mesh.kv.try_cas(detection_key(detection_id)) as cas:
        try:
            rec = DetectionRecord.model_validate_json(cas.value)
        except Exception:
            return False
        if rec.state != "pending":
            return False
        rec.state = f"assigned:{mesh.instance_id}"
        rec.last_updated = time.time()
        cas.value = rec.model_dump_json()
    return cas.committed


async def _complete(
    mesh: AgentMesh, detection_id: str, survey: SurveyResult,
) -> bool:
    """CAS-transition the detection from ``assigned:{my_instance_id}`` to
    ``surveyed`` and attach the ``SurveyResult`` payload.

    Uses ``try_cas`` (not the raising ``cas``) so a stale CAS write from
    a chaos-killed peer (Phase 4) does not crash the agent; race-loss is
    logged at the call site.
    """
    async with mesh.kv.try_cas(detection_key(detection_id)) as cas:
        try:
            rec = DetectionRecord.model_validate_json(cas.value)
        except Exception:
            return False
        rec.state = "surveyed"
        rec.survey = survey
        rec.last_updated = time.time()
        cas.value = rec.model_dump_json()
    return cas.committed


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------


def build_agent(mesh: AgentMesh, state: DroneState) -> None:
    """Register the low-alt.drone agent on ``mesh``.

    The handler is closed over ``state`` (per-process) and ``mesh``
    (per-process) so each of the 5 orchestrator-spawned processes gets
    its own registration with its own ``mesh.instance_id``.
    """

    @mesh.agent(
        AgentSpec(
            name="low-alt.drone",
            description=(
                "Low-altitude survey drone; KV-CAS-elected on pending "
                "detections, simulates travel + survey, writes the "
                "SurveyResult. Use for close-range intelligence on a "
                "DetectionRecord; do NOT use to suppress fires or extract "
                "people."
            ),
        ),
        # KV-watch source: kv_source("wildfire.detection.*") -- kept as an
        # f-string against DETECTION_PREFIX so a future namespace tweak
        # is a one-file change in demos.wildfire.core.keys.
        sources=[mesh.kv_source(f"{DETECTION_PREFIX}.*", on_init="replay")],
    )
    async def drone(entry: KVEntry[DetectionRecord]) -> None:
        # DELETE: detections are not retracted in v1; ignore.
        if entry.operation == "DELETE":
            return
        try:
            # One survey at a time per drone instance.
            if state.fleet_state != "free":
                return
            rec = entry.value
            if rec.state != "pending":
                return
            if not await _is_closest_free(mesh, state, rec.coords):
                return
            if not await _claim(mesh, rec.detection_id):
                return

            # We won the election. Travel + survey.
            state.fleet_state = "busy"
            state.assignment_id = rec.detection_id

            # Travel out (interpolator task animates current_coords).
            travel_s = max(
                0.5, _distance_km(state.current_coords, rec.coords) / DRONE_SPEED_KM_S,
            )
            state.travel_src = state.current_coords
            state.travel_dst = rec.coords
            state.travel_start = time.time()
            state.travel_duration = travel_s
            await asyncio.sleep(travel_s)
            state.current_coords = rec.coords
            state.travel_duration = 0.0

            # Simulate sensor sweep over the area.
            await asyncio.sleep(DRONE_SURVEY_DURATION_S)
            survey = SurveyResult(
                surveyor_instance_id=mesh.instance_id,
                timestamp=time.time(),
                fire_visible=True,
                persons_detected=0,
                structures_visible=0,
                notes="",
            )

            # CAS-write the surveyed transition. On loss (chaos-killed peer
            # wrote a stale record), log and continue: we still own the
            # heartbeat-state lifecycle and must return to free.
            committed = await _complete(mesh, rec.detection_id, survey)
            if committed:
                # A-08: the only Phase 1 pubsub from this agent.
                await mesh.publish(f"mesh.survey.{mesh.instance_id}", survey)
                _log.info(
                    "surveyed detection %s @ (%.2f, %.2f)",
                    rec.detection_id,
                    rec.coords.x,
                    rec.coords.y,
                )
            else:
                _log.warning(
                    "surveyed-CAS lost for detection %s (race?)",
                    rec.detection_id,
                )

            # Travel back to HQ. Same interpolation pattern.
            return_s = max(
                0.5, _distance_km(state.current_coords, HQ) / DRONE_SPEED_KM_S,
            )
            state.travel_src = state.current_coords
            state.travel_dst = HQ
            state.travel_start = time.time()
            state.travel_duration = return_s
            await asyncio.sleep(return_s)
            state.current_coords = HQ
            state.travel_duration = 0.0

            state.fleet_state = "free"
            state.assignment_id = None
        except Exception as e:
            # One bad entry must not abort the agent. Reset state so the
            # heartbeat continues to advertise this drone as free.
            _log.warning("drone handler error on key %r: %s", entry.key, e)
            state.fleet_state = "free"
            state.assignment_id = None
            state.travel_duration = 0.0


# ---------------------------------------------------------------------------
# Process entry point: `python -m demos.wildfire.fleet.drone`
# ---------------------------------------------------------------------------


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    state = DroneState(
        current_coords=HQ,
        fleet_state="free",
        assignment_id=None,
        travel_src=HQ,
        travel_dst=HQ,
    )
    build_agent(mesh, state)

    async with mesh:
        interp = asyncio.create_task(_interpolator(state))
        chaos = asyncio.create_task(chaos_kill_listener(mesh))
        hb = asyncio.create_task(
            heartbeat_loop(
                mesh,
                zone="low-alt",
                fleet_type="drone",
                get_state=lambda: state.fleet_state,
                get_coords=lambda: state.current_coords,
                get_assignment=lambda: state.assignment_id,
            )
        )
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            interp.cancel()
            hb.cancel()
            chaos.cancel()
            for task in (interp, hb, chaos):
                with contextlib.suppress(asyncio.CancelledError):
                    await task


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
