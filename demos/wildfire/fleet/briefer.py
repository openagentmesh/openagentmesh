"""briefer: LLM peer correlating detections into incidents + briefing cadence.

The briefer watches the detection KV namespace, clusters detections into
incidents (coords + time heuristic), and emits schema-validated
``IncidentBriefing`` payloads on a 30 s cadence (or when an incident's
unbriefed event count crosses ``BRIEFER_EVENT_THRESHOLD``). Two instances
run concurrently (``BRIEFER_COUNT``); this module is one process = one
instance, like ``uav.py``.

Per ``km/specs/wildfire/briefer.md`` with these v1 decisions:

- **Two registered agents, one process.** ADR-0052 binds one handler shape
  per agent, and the two sources carry different payloads
  (``KVEntry[DetectionRecord]`` vs ``MeshMessage[SurveyResult]``). Following
  the dashboard multi-feed precedent, the process registers ``briefer``
  (KV-watch, the real work) and ``briefer.survey-feed`` (pubsub visibility).
- **Incident-id agreement via the detection record.** Both instances observe
  every detection, so "create a fresh ``inc-{uuid}``" would systematically
  produce two incidents per isolated detection. The agreement point is a CAS
  on ``DetectionRecord.incident_id`` (the contract field documented as "set
  by briefer once correlated"): the ``try_cas`` winner's id is canonical, the
  loser adopts it from the fresh read. Once the id is agreed, all
  ``IncidentState`` writes are same-key and safely CAS/create-gated.
- **Tick gating via CAS on ``last_briefing_at``.** The check loop sub-samples
  the 30 s cadence; for a due incident the instance that commits the
  ``try_cas_model`` bump produces the briefing, the other silently yields.
  ``last_briefing_at = 0.0`` on a new incident means the first check pass
  briefs it immediately (good demo latency).
- **LLM facts vs judgement.** ``incident_id``, ``sources``, ``issued_at``,
  ``issuing_instance_id`` are facts this process knows; the LLM only fills
  the judgement fields (``BriefingDraft``). On ``LLMUnavailable`` a degraded
  briefing is emitted: fixed summary, severity from a deterministic
  heuristic off max detection severity, ``confidence=0.0``. The model id
  comes from config ``LLM_MODEL_BRIEFER``; never hardcoded here.
- **Resolution, best-effort v1.** An incident whose cached detections are all
  ``surveyed`` with nothing unbriefed for 2 consecutive check passes is
  CAS-marked resolved. No fire-sim temperature check, no stale-assignment
  watchdog (spec open questions; documented limitations).
- **No heartbeat.** ``FleetMemberState.fleet_type`` is a closed Literal of
  the five fleet types; the briefer is an LLM peer, not a fleet member.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import os
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from nats.js.errors import KeyNotFoundError, KeyWrongLastSequenceError
from pydantic import BaseModel, Field, ValidationError

from demos.wildfire.core.config import (
    BRIEFER_CLUSTER_RADIUS_KM,
    BRIEFER_CLUSTER_WINDOW_S,
    BRIEFER_EVENT_THRESHOLD,
    BRIEFER_TICK_INTERVAL_S,
    LLM_MODEL_BRIEFER,
    STALE_ASSIGNMENT_AFTER_S,
)
from demos.wildfire.core.contracts import (
    DetectionRecord,
    FleetMemberState,
    IncidentBriefing,
    IncidentState,
    RecommendedAction,
    SurveyResult,
)
from demos.wildfire.core.keys import (
    DETECTION_PREFIX,
    INCIDENT_PREFIX,
    detection_key,
    fleet_key,
    incident_key,
)
from demos.wildfire.core.llm import LLMUnavailable, structured_llm_call
from openagentmesh import AgentMesh
from openagentmesh._context import KVEntry
from openagentmesh._errors import KVKeyExists
from openagentmesh._models import AgentSpec
from openagentmesh._sources import MeshMessage

_log = logging.getLogger("wildfire.briefer")

SeverityLit = Literal["low", "med", "high", "critical"]

# Check-loop cadence: sub-samples the 30 s briefing interval 6x (= 5 s).
# Derived from config so this module adds no free-standing magic number
# (config.py is frozen for this task).
_CHECK_INTERVAL_S: float = BRIEFER_TICK_INTERVAL_S / 6.0

# v1 resolution: consecutive quiet check passes before an incident is
# CAS-marked resolved. "Quiet" = all cached detections surveyed and nothing
# unbriefed. Known limitation: no fire-sim temperature check.
_RESOLVE_QUIET_TICKS: int = 2

_CAS_RETRIES: int = 10

_SEVERITY_RANK: dict[str, int] = {"low": 0, "med": 1, "high": 2, "critical": 3}


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested directly, no NATS / no LLM)
# ---------------------------------------------------------------------------


def new_incident_id() -> str:
    """Fresh incident id: ``inc-`` + 8 hex chars."""
    return f"inc-{uuid.uuid4().hex[:8]}"


def find_merge_target(
    detection: DetectionRecord,
    incidents: Mapping[str, Sequence[DetectionRecord]],
) -> str | None:
    """Return the id of the first open incident ``detection`` clusters into.

    Merge rule (spec "Correlation logic"): any existing detection of the
    incident within ``BRIEFER_CLUSTER_RADIUS_KM`` AND within
    ``BRIEFER_CLUSTER_WINDOW_S`` by ``created_at``. Returns ``None`` when no
    incident matches (caller creates a new one). Pure: no I/O, no clock.
    """
    for incident_id, records in incidents.items():
        for rec in records:
            close = (
                math.hypot(
                    detection.coords.x - rec.coords.x,
                    detection.coords.y - rec.coords.y,
                )
                <= BRIEFER_CLUSTER_RADIUS_KM
            )
            recent = abs(detection.created_at - rec.created_at) <= BRIEFER_CLUSTER_WINDOW_S
            if close and recent:
                return incident_id
    return None


def severity_from_max(max_severity: float) -> SeverityLit:
    """Deterministic severity heuristic off the max detection severity."""
    if max_severity >= 0.8:
        return "critical"
    if max_severity >= 0.6:
        return "high"
    if max_severity >= 0.35:
        return "med"
    return "low"


def severity_from_detections(detections: Sequence[DetectionRecord]) -> SeverityLit:
    """Heuristic severity for a detection set (empty set degrades to low)."""
    return severity_from_max(max((r.severity for r in detections), default=0.0))


def _max_severity(a: SeverityLit, b: SeverityLit) -> SeverityLit:
    return a if _SEVERITY_RANK[a] >= _SEVERITY_RANK[b] else b


def degraded_actions(severity: SeverityLit, persons_estimated: int) -> list[RecommendedAction]:
    """Deterministic recommended actions for the degraded (no-LLM) path."""
    base: dict[SeverityLit, list[RecommendedAction]] = {
        "low": ["monitor"],
        "med": ["dispatch_ffunit"],
        "high": ["dispatch_heli", "dispatch_ffunit"],
        "critical": ["dispatch_heli", "dispatch_ffunit", "evacuate"],
    }
    actions = list(base[severity])
    if persons_estimated > 0:
        actions.append("dispatch_medevac")
    return actions


def degraded_briefing(
    *,
    incident_id: str,
    detections: Sequence[DetectionRecord],
    issuing_instance_id: str,
    now: float,
) -> IncidentBriefing:
    """Well-formed fallback briefing when the LLM is unavailable (spec

    "Reliability"): fixed summary, heuristic severity, survey-summed counts,
    ``confidence=0.0``.
    """
    severity = severity_from_detections(detections)
    persons = sum(r.survey.persons_detected for r in detections if r.survey is not None)
    structures = sum(r.survey.structures_visible for r in detections if r.survey is not None)
    return IncidentBriefing(
        incident_id=incident_id,
        severity=severity,
        summary="Briefing unavailable, see KV record",
        persons_estimated=persons,
        structures_at_risk=structures,
        recommended_actions=degraded_actions(severity, persons),
        sources=[r.detection_id for r in detections],
        confidence=0.0,
        issued_at=now,
        issuing_instance_id=issuing_instance_id,
    )


# ---------------------------------------------------------------------------
# LLM briefing assembly
# ---------------------------------------------------------------------------


class BriefingDraft(BaseModel):
    """LLM-facing output schema: judgement fields only.

    The facts (``incident_id``, ``sources``, ``issued_at``,
    ``issuing_instance_id``) are assembled by :func:`compose_briefing`; the
    LLM never gets the chance to invent them.
    """

    severity: SeverityLit
    summary: str = Field(max_length=280)
    persons_estimated: int = Field(ge=0)
    structures_at_risk: int = Field(ge=0)
    recommended_actions: list[RecommendedAction]
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


_SYSTEM_PROMPT = (
    "You are the incident briefer for a wildfire response agent mesh. "
    "You receive one incident as structured JSON: incident metadata plus its "
    "detection records (thermal severity 0..1, coords in km from HQ) and any "
    "drone survey results. Produce a concise operational briefing for a "
    "human fire commander. Base every number on the provided records; do not "
    "invent data. The summary must be a single sentence under 280 characters."
)


async def compose_briefing(
    *,
    incident_id: str,
    detections: Sequence[DetectionRecord],
    issuing_instance_id: str,
    now: float | None = None,
) -> IncidentBriefing:
    """Build the full ``IncidentBriefing`` for an incident.

    Prompt content is structured data only (spec "Behaviour notes"): the
    incident metadata and detection/survey records serialized as JSON. On
    ``LLMUnavailable`` (no key, timeout, invalid output after retry) the
    degraded briefing is returned instead; this function always yields a
    valid ``IncidentBriefing``.
    """
    issued_at = time.time() if now is None else now
    sources = [r.detection_id for r in detections]
    user_payload = {
        "incident_id": incident_id,
        "issued_at": issued_at,
        "detections": [r.model_dump() for r in detections],
    }
    try:
        draft = await structured_llm_call(
            model=LLM_MODEL_BRIEFER,
            system=_SYSTEM_PROMPT,
            user_content=json.dumps(user_payload),
            output_model=BriefingDraft,
        )
    except LLMUnavailable as e:
        _log.warning(
            "LLM unavailable for incident %s: %s; emitting degraded briefing",
            incident_id,
            e,
        )
        return degraded_briefing(
            incident_id=incident_id,
            detections=detections,
            issuing_instance_id=issuing_instance_id,
            now=issued_at,
        )
    return IncidentBriefing(
        incident_id=incident_id,  # fact: ours, never the LLM's
        severity=draft.severity,
        summary=draft.summary,
        persons_estimated=draft.persons_estimated,
        structures_at_risk=draft.structures_at_risk,
        recommended_actions=draft.recommended_actions,
        sources=sources,  # fact: ours
        confidence=draft.confidence,
        issued_at=issued_at,  # fact: ours
        issuing_instance_id=issuing_instance_id,  # fact: ours
    )


# ---------------------------------------------------------------------------
# In-memory correlation cache (per instance; KV is the durable truth)
# ---------------------------------------------------------------------------


@dataclass
class IncidentCache:
    incident_id: str
    detections: dict[str, DetectionRecord] = field(default_factory=dict)
    unbriefed_events: int = 0
    quiet_ticks: int = 0
    resolved: bool = False


@dataclass
class BrieferState:
    incidents: dict[str, IncidentCache] = field(default_factory=dict)

    def open_incident_detections(self) -> dict[str, list[DetectionRecord]]:
        """Snapshot for :func:`find_merge_target`: open incidents only."""
        return {
            iid: list(c.detections.values())
            for iid, c in self.incidents.items()
            if not c.resolved
        }


def _is_quiet(cache: IncidentCache) -> bool:
    """True when the incident has no fleet activity left and nothing unbriefed."""
    return (
        bool(cache.detections)
        and cache.unbriefed_events == 0
        and all(r.state == "surveyed" for r in cache.detections.values())
    )


def _incident_for_surveyor(state: BrieferState, surveyor_instance_id: str) -> IncidentCache | None:
    """Locate the open incident a survey pubsub event belongs to.

    ``SurveyResult`` carries no detection id, so match on the drone instance:
    a detection still in ``assigned:{surveyor}`` state, or one whose attached
    survey came from that surveyor (KV echo already processed).
    """
    assigned = f"assigned:{surveyor_instance_id}"
    for cache in state.incidents.values():
        if cache.resolved:
            continue
        for rec in cache.detections.values():
            if rec.state == assigned:
                return cache
            if rec.survey is not None and rec.survey.surveyor_instance_id == surveyor_instance_id:
                return cache
    return None


# ---------------------------------------------------------------------------
# Durable KV incident store (single mesh-context bucket, wildfire.incident.*)
# ---------------------------------------------------------------------------


async def _agree_incident_id(
    mesh: AgentMesh, state: BrieferState, rec: DetectionRecord
) -> str | None:
    """Agree on the incident id for an uncorrelated detection.

    Computes merge-target-or-fresh-id locally, then CASes it onto
    ``DetectionRecord.incident_id``. Both briefer instances race here; the
    ``try_cas`` winner's id is canonical and the loser adopts it from the
    fresh read on retry. Conflicts with drone claim CASes simply retry.
    """
    chosen = find_merge_target(rec, state.open_incident_detections()) or new_incident_id()
    key = detection_key(rec.detection_id)
    for _ in range(5):
        try:
            ctx = mesh.kv.try_cas_model(key, DetectionRecord)
            async with ctx as entry:
                if entry.value.incident_id is None:
                    entry.value.incident_id = chosen
        except KeyNotFoundError:
            return None
        if entry.committed:
            return entry.value.incident_id
        await asyncio.sleep(0.05)
    _log.warning("incident-id agreement failed for %s after 5 CAS attempts", rec.detection_id)
    return None


async def _upsert_incident(
    mesh: AgentMesh,
    incident_id: str,
    detection_id: str,
    det_severity: SeverityLit,
) -> None:
    """Ensure the durable ``IncidentState`` exists and contains ``detection_id``.

    CAS-merge when present, ``create`` (put-if-absent) when new. Both
    instances race on the same key; retry-on-mismatch is the intended
    behaviour. ``last_briefing_at=0.0`` marks a never-briefed incident, so
    the first tick pass briefs it immediately.
    """
    key = incident_key(incident_id)
    for _ in range(_CAS_RETRIES):
        try:
            async with mesh.kv.cas_model(key, IncidentState) as entry:
                st = entry.value
                if detection_id not in st.detection_ids:
                    st.detection_ids.append(detection_id)
                st.severity = _max_severity(st.severity, det_severity)
            return
        except KeyNotFoundError:
            fresh = IncidentState(
                incident_id=incident_id,
                detection_ids=[detection_id],
                last_briefing_at=0.0,
                briefings=[],
                severity=det_severity,
            )
            try:
                await mesh.kv.create(key, fresh)
                return
            except KVKeyExists:
                continue  # peer created it concurrently; CAS-merge on retry
        except KeyWrongLastSequenceError:
            continue  # CAS conflict with the peer instance; re-read and retry
    _log.warning("incident upsert failed for %s after %d CAS retries", incident_id, _CAS_RETRIES)


async def _append_briefing(mesh: AgentMesh, briefing: IncidentBriefing) -> None:
    """CAS-append a produced briefing to the incident's durable history."""
    key = incident_key(briefing.incident_id)
    for _ in range(_CAS_RETRIES):
        try:
            async with mesh.kv.cas_model(key, IncidentState) as entry:
                entry.value.briefings.append(briefing)
                entry.value.severity = briefing.severity
            return
        except KeyNotFoundError:
            _log.warning("incident %s vanished before briefing append", briefing.incident_id)
            return
        except KeyWrongLastSequenceError:
            continue
    _log.warning(
        "briefing append failed for %s after %d CAS retries",
        briefing.incident_id,
        _CAS_RETRIES,
    )


async def _resolve_incident(mesh: AgentMesh, incident_id: str, now: float) -> None:
    """Best-effort CAS resolution; losing the race is fine (peer resolved it)."""
    try:
        async with mesh.kv.try_cas_model(incident_key(incident_id), IncidentState) as entry:
            if not entry.value.resolved:
                entry.value.resolved = True
                entry.value.resolved_at = now
    except KeyNotFoundError:
        return


async def _ingest_detection(mesh: AgentMesh, state: BrieferState, rec: DetectionRecord) -> None:
    """Correlate one detection lifecycle event into cache + durable store."""
    incident_id = rec.incident_id
    if incident_id is None:
        incident_id = await _agree_incident_id(mesh, state, rec)
        if incident_id is None:
            return  # next KV echo of this record retries the agreement
        rec = rec.model_copy(update={"incident_id": incident_id})
    await _upsert_incident(mesh, incident_id, rec.detection_id, severity_from_max(rec.severity))
    cache = state.incidents.setdefault(incident_id, IncidentCache(incident_id=incident_id))
    old = cache.detections.get(rec.detection_id)
    cache.detections[rec.detection_id] = rec
    if old is None or old.state != rec.state:
        # New detection or a state transition (pending -> assigned:{id} ->
        # surveyed): counts toward BRIEFER_EVENT_THRESHOLD. Our own
        # incident-id CAS echo has an unchanged state and does not count.
        cache.unbriefed_events += 1
        cache.quiet_ticks = 0


# ---------------------------------------------------------------------------
# Briefing tick loop (pattern: fire_sim._spread_loop)
# ---------------------------------------------------------------------------


async def _briefing_inputs(
    mesh: AgentMesh, cache: IncidentCache, st: IncidentState
) -> list[DetectionRecord]:
    """Detection records for the briefing, cache-first with KV fallback."""
    detections: list[DetectionRecord] = []
    for did in st.detection_ids:
        rec = cache.detections.get(did)
        if rec is None:
            try:
                rec = await mesh.kv.get_model(detection_key(did), DetectionRecord)
            except (KeyNotFoundError, ValidationError) as e:
                _log.warning("could not load detection %s: %s", did, e)
                continue
            cache.detections[did] = rec
        detections.append(rec)
    return detections


async def reclaim_stale_assignments(mesh: AgentMesh, now: float | None = None) -> list[str]:
    """Chaos recovery watchdog: dead drone's detections go back to pending.

    A detection in ``assigned:{drone_instance_id}`` whose drone heartbeat is
    at least ``STALE_ASSIGNMENT_AFTER_S`` stale (or missing) is CAS-flipped
    back to ``pending``. The PUT re-fires every sibling drone's kv_source,
    so a new election claims the abandoned detection within seconds; the
    cascade never stalls on a chaos kill. Returns the reclaimed ids.
    """
    now = time.time() if now is None else now
    reclaimed: list[str] = []
    raw = await mesh.kv.list(f"{DETECTION_PREFIX}.*")
    for entry in raw:
        try:
            rec = DetectionRecord.model_validate_json(entry.value)
        except ValidationError:
            continue
        state_str = str(rec.state)
        if not state_str.startswith("assigned:"):
            continue
        surveyor = state_str.split(":", 1)[1]

        alive = False
        try:
            member = await mesh.kv.get_model(
                fleet_key("low-alt", "drone", surveyor), FleetMemberState
            )
            alive = now - member.last_updated < STALE_ASSIGNMENT_AFTER_S
        except (KeyNotFoundError, ValidationError):
            alive = False  # no heartbeat record at all: treat as dead
        if alive:
            continue

        try:
            ctx = mesh.kv.try_cas_model(detection_key(rec.detection_id), DetectionRecord)
            async with ctx as gate:
                if str(gate.value.state) == state_str:  # still stuck on the dead drone
                    gate.value.state = "pending"
                    gate.value.last_updated = now
        except KeyNotFoundError:
            continue
        if gate.committed and gate.attempted_write:
            reclaimed.append(rec.detection_id)
            _log.warning(
                "reclaimed detection %s from dead drone %s", rec.detection_id, surveyor
            )
    return reclaimed


async def _tick_once(mesh: AgentMesh, state: BrieferState, now: float | None = None) -> None:
    """One pass over the durable incident store: reclaim, resolve, gate, brief."""
    now = time.time() if now is None else now
    await reclaim_stale_assignments(mesh, now)
    raw = await mesh.kv.list(f"{INCIDENT_PREFIX}.*")
    for raw_entry in raw:
        try:
            st = IncidentState.model_validate_json(raw_entry.value)
        except ValidationError:
            # Stale-schema keys replay across demo boots (see AGENT_NOTES);
            # one bad record must not kill the tick pass.
            _log.warning("skipping malformed incident record at %r", raw_entry.key)
            continue

        cache = state.incidents.setdefault(st.incident_id, IncidentCache(incident_id=st.incident_id))
        if st.resolved:
            cache.resolved = True
            continue

        if _is_quiet(cache):
            cache.quiet_ticks += 1
        else:
            cache.quiet_ticks = 0
        if cache.quiet_ticks >= _RESOLVE_QUIET_TICKS:
            await _resolve_incident(mesh, st.incident_id, now)
            cache.resolved = True
            continue

        due = (
            now - st.last_briefing_at >= BRIEFER_TICK_INTERVAL_S
            or cache.unbriefed_events >= BRIEFER_EVENT_THRESHOLD
        )
        if not due:
            continue

        # Queue-group-equivalent gate: CAS-bump last_briefing_at first. The
        # winner produces the briefing; the loser silently yields. The due
        # condition is re-checked on the fresh read inside the CAS.
        try:
            ctx = mesh.kv.try_cas_model(incident_key(st.incident_id), IncidentState)
            async with ctx as gate:
                fresh = gate.value
                if not fresh.resolved and (
                    now - fresh.last_briefing_at >= BRIEFER_TICK_INTERVAL_S
                    or cache.unbriefed_events >= BRIEFER_EVENT_THRESHOLD
                ):
                    fresh.last_briefing_at = now
        except KeyNotFoundError:
            continue
        if not (gate.committed and gate.attempted_write):
            continue

        detections = await _briefing_inputs(mesh, cache, fresh)
        if not detections:
            continue
        briefing = await compose_briefing(
            incident_id=st.incident_id,
            detections=detections,
            issuing_instance_id=mesh.instance_id,
            now=now,
        )
        # Pubsub-write: mesh.briefing.{incident_id} (spec "Outputs").
        await mesh.publish(f"mesh.briefing.{briefing.incident_id}", briefing)
        await _append_briefing(mesh, briefing)
        cache.unbriefed_events = 0
        _log.info(
            "briefed incident %s (severity=%s confidence=%.2f sources=%d)",
            briefing.incident_id,
            briefing.severity,
            briefing.confidence,
            len(briefing.sources),
        )


async def _tick_loop(mesh: AgentMesh, state: BrieferState) -> None:
    """Check every ``_CHECK_INTERVAL_S`` seconds until cancelled."""
    try:
        while True:
            await asyncio.sleep(_CHECK_INTERVAL_S)
            try:
                await _tick_once(mesh, state)
            except Exception as e:
                _log.warning("briefer tick failed: %s", e)
    except asyncio.CancelledError:
        return


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------


def build_agent(mesh: AgentMesh, state: BrieferState | None = None) -> BrieferState:
    """Register the briefer agents on ``mesh``; returns the shared state.

    Handlers are bound but not started until the surrounding
    ``async with mesh:`` block (same contract as ``uav.build_agent``). The
    tick loop is NOT started here; ``_main`` owns it so tests can exercise
    correlation without the cadence machinery.
    """
    state = state if state is not None else BrieferState()

    @mesh.agent(
        AgentSpec(
            name="briefer",
            description=(
                "LLM incident briefer: correlates wildfire detections into "
                "incidents and emits schema-validated IncidentBriefing "
                "summaries for human operators. Use to understand incident "
                "status; do NOT use to dispatch fleets (use the tasker or "
                "direct fleet calls)."
            ),
        ),
        # KV-watch source: kv_source("wildfire.detection.*") -- expanded
        # literal kept in this comment for cross-repo greps; the canonical
        # constant is demos.wildfire.core.keys.DETECTION_PREFIX. Detection
        # keys carry one trailing segment, so `*` is correct here.
        sources=[mesh.kv_source(f"{DETECTION_PREFIX}.*", on_init="replay")],
    )
    async def briefer(entry: KVEntry[DetectionRecord]) -> None:
        # DELETE: detections are not retracted in v1; ignore (on DELETE the
        # entry arrives with value=None, so touching entry.value would throw).
        if entry.operation == "DELETE":
            return
        try:
            await _ingest_detection(mesh, state, entry.value)
        except Exception as e:
            # One bad record does not kill the agent.
            _log.warning("briefer handler error on key %r: %s", entry.key, e)

    @mesh.agent(
        AgentSpec(
            name="briefer.survey-feed",
            description=(
                "Briefer fast-reaction survey visibility: observes drone "
                "survey broadcasts and keeps incident activity fresh. "
                "Read-only observability feed; the detection KV record "
                "remains the source of truth."
            ),
        ),
        # Broadcast, deliberately NO queue_group: both briefer instances keep
        # independent correlation caches, so both must observe every survey.
        # Tick gating is the KV CAS above, not a queue group (spec
        # "Lifecycle" + sdk-desiderata #3 note).
        sources=[mesh.subject_source("mesh.survey.>")],
    )
    async def briefer_survey(msg: MeshMessage[SurveyResult]) -> None:
        survey = msg.payload
        if survey is None:
            return
        cache = _incident_for_surveyor(state, survey.surveyor_instance_id)
        if cache is not None:
            # Activity marker only: the KV surveyed transition is the
            # authoritative event counter (avoids double counting the same
            # survey via both sources).
            cache.quiet_ticks = 0

    return state


# ---------------------------------------------------------------------------
# Process entry point: `python -m demos.wildfire.fleet.briefer`
# ---------------------------------------------------------------------------


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    state = build_agent(mesh)

    async with mesh:
        tick = asyncio.create_task(_tick_loop(mesh, state))
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            tick.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tick


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
