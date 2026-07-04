"""narrator: LLM peer producing the demo's "story so far" voiceover.

Per ``km/specs/wildfire/narrator.md``: every ``NARRATOR_INTERVAL_S`` (5 min)
the narrator summarizes swarm activity across all incidents into one
paragraph (max 1000 chars, enforced by the frozen ``Narrative`` contract)
and publishes it on ``mesh.swarm.narrative``.

Shape:

- Single registered agent ``narrator`` (single instance, not invocable:
  the handler takes a ``MeshMessage`` envelope, so the runtime marks it
  source-driven / background per ADR-0052).
- Two subject sources feed a rolling in-memory window
  (:class:`NarratorWindow`): ``mesh.briefing.>`` (``IncidentBriefing``,
  counts + incident ids only) and ``mesh.swarm.stats`` (``SwarmStats``,
  latest numbers win). The source handler only appends to the window;
  all heavy lifting happens on the timer tick.
- A background timer task (``_narrate_loop``, same pattern as fire-sim's
  ``_spread_loop``) drains the window every ``NARRATOR_INTERVAL_S``,
  reads incident summaries via ``mesh.kv.list_models`` on the
  ``wildfire.incident.*`` prefix (single ``mesh-context`` bucket, no
  ``bucket`` kwarg), makes ONE :func:`structured_llm_call`
  (``LLM_MODEL_NARRATOR``, Haiku tier), and publishes the assembled
  ``Narrative`` via ``mesh.publish``.

Reliability (per spec "Reliability"):

- :class:`LLMUnavailable` -> log and skip the period. The window is reset
  BEFORE the LLM call, so a failed period never retries into the next one
  and never produces degraded output.
- Empty window + no incidents in KV -> skip silently (no LLM call, no
  publish). Stats arrive every 10 s regardless of activity, so a
  stats-only window still counts as silence: we don't narrate silence.

Boot UX::

    python -m demos.wildfire.fleet.narrator

Reads ``NATS_URL`` (default ``nats://127.0.0.1:4222``); the orchestrator
exports it for child processes.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import time
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from demos.wildfire.core.config import LLM_MODEL_NARRATOR, NARRATOR_INTERVAL_S
from demos.wildfire.core.contracts import (
    IncidentBriefing,
    IncidentState,
    Narrative,
    SwarmStats,
)
from demos.wildfire.core.keys import INCIDENT_PREFIX
from demos.wildfire.core.llm import LLMUnavailable, structured_llm_call
from openagentmesh import AgentMesh, AgentSpec, MeshMessage

_log = logging.getLogger("wildfire.narrator")


# ---------------------------------------------------------------------------
# Subjects (pubsub; KV keys come from demos.wildfire.core.keys)
# ---------------------------------------------------------------------------

BRIEFING_SUBJECT_PATTERN = "mesh.briefing.>"
STATS_SUBJECT = "mesh.swarm.stats"
NARRATIVE_SUBJECT = "mesh.swarm.narrative"

# NATS wildcard is mandatory on kv.list/list_models; bare prefixes return []
# (see tests/wildfire/unit/test_uav.py DETECTION_WILDCARD precedent).
INCIDENT_WILDCARD = f"{INCIDENT_PREFIX}.>"


def _narrative_text_max() -> int:
    """Read ``Narrative.text``'s max_length off the frozen contract.

    The contract is the single source of truth for the 1000-char cap; we
    truncate defensively to it before constructing the model (Pydantic
    raises on overflow, it does not truncate).
    """
    for meta in Narrative.model_fields["text"].metadata:
        max_len = getattr(meta, "max_length", None)
        if max_len is not None:
            return int(max_len)
    raise RuntimeError("Narrative.text lost its max_length constraint")


_TEXT_MAX: int = _narrative_text_max()


# ---------------------------------------------------------------------------
# Rolling window (pure, unit-testable without NATS)
# ---------------------------------------------------------------------------


@dataclass
class WindowSnapshot:
    """Frozen view of one narrate period, taken at the timer tick."""

    period_start: float
    briefing_count: int
    incident_ids: list[str]  # sorted, deduped ids seen in window briefings
    latest_stats: SwarmStats | None


@dataclass
class NarratorWindow:
    """Rolling in-memory event window between narrate ticks.

    Source handlers only append here (cheap, non-blocking); the narrate
    loop drains it via :meth:`reset`. Per spec "State": briefing count,
    incident ids seen this window, latest stats numbers. No raw text from
    external agents is retained (prompt sources are KV incident summaries).
    """

    period_start: float = field(default_factory=time.time)
    briefing_count: int = 0
    incident_ids: set[str] = field(default_factory=set)
    latest_stats: SwarmStats | None = None

    def add_briefing(self, briefing: IncidentBriefing) -> None:
        self.briefing_count += 1
        self.incident_ids.add(briefing.incident_id)

    def add_stats(self, stats: SwarmStats) -> None:
        self.latest_stats = stats  # latest numbers win

    def reset(self, now: float) -> WindowSnapshot:
        """Snapshot the accumulated window and start a fresh period at ``now``."""
        snapshot = WindowSnapshot(
            period_start=self.period_start,
            briefing_count=self.briefing_count,
            incident_ids=sorted(self.incident_ids),
            latest_stats=self.latest_stats,
        )
        self.period_start = now
        self.briefing_count = 0
        self.incident_ids = set()
        self.latest_stats = None
        return snapshot


# ---------------------------------------------------------------------------
# LLM output model (internal; the wire contract is Narrative)
# ---------------------------------------------------------------------------


class NarrationOutput(BaseModel):
    """Structured output of the narration LLM call.

    ``period_start`` / ``period_end`` are facts the narrator already knows,
    so the LLM only produces the paragraph and the ids it referenced; the
    full ``Narrative`` is assembled locally.
    """

    text: str = Field(description="One narrative paragraph, plain text.")
    incident_ids_referenced: list[str] = Field(
        default_factory=list,
        description="Incident ids actually mentioned in the paragraph.",
    )


_SYSTEM_PROMPT = (
    "You are the mission narrator for an autonomous wildfire-response swarm. "
    "Write the 'story so far' for the reporting window as ONE plain-text "
    f"paragraph of at most {_TEXT_MAX} characters. Ground every statement in "
    "the data provided; never invent incidents, numbers, or outcomes. Refer "
    "to incidents by their ids and list the ids you actually mentioned in "
    "incident_ids_referenced."
)


def _render_prompt(
    snapshot: WindowSnapshot,
    incidents: list[IncidentState],
    period_end: float,
) -> str:
    """Render the user prompt from KV incident summaries + window counters.

    Per spec "Behaviour notes": prompt sources are incident summaries from
    KV plus counters from the narrate window. No raw external-agent text.
    """
    minutes = max(0.0, period_end - snapshot.period_start) / 60.0
    lines = [
        f"Reporting window: the last {minutes:.1f} minutes.",
        f"Briefings received this window: {snapshot.briefing_count}.",
    ]
    if snapshot.incident_ids:
        lines.append(
            "Incidents briefed this window: " + ", ".join(snapshot.incident_ids) + "."
        )
    if snapshot.latest_stats is not None:
        s = snapshot.latest_stats
        lines.append(
            "Latest swarm stats: "
            f"{s.uavs_active}/{s.uavs_total} UAVs, "
            f"{s.drones_active}/{s.drones_total} drones, "
            f"{s.helis_active}/{s.helis_total} helis, "
            f"{s.ffunits_active}/{s.ffunits_total} fire units, "
            f"{s.medevacs_active}/{s.medevacs_total} medevacs active; "
            f"{s.incidents_open} incidents open, {s.incidents_resolved} resolved; "
            f"{s.fires_detected_total} fires detected and "
            f"{s.persons_recovered_total} persons recovered in total."
        )
    if incidents:
        lines.append("Incident records (from the shared incident registry):")
        for inc in incidents:
            status = "resolved" if inc.resolved else "open"
            latest = inc.briefings[-1].summary if inc.briefings else "(no briefing yet)"
            lines.append(
                f"- {inc.incident_id} [{inc.severity}, {status}, "
                f"{len(inc.detection_ids)} detections]: {latest}"
            )
    return "\n".join(lines)


async def compose_narrative(
    snapshot: WindowSnapshot,
    incidents: list[IncidentState],
    *,
    period_end: float,
) -> Narrative | None:
    """One narrate step: window + incidents in, ``Narrative`` (or None) out.

    Returns ``None`` (skip the period) when:

    - Nothing happened: no briefings this window AND no incident ids seen
      AND no incidents in KV. Stats alone don't count (they tick every 10 s
      regardless of activity); we don't narrate silence. No LLM call is made.
    - The LLM is unavailable (per spec: log and skip, no retry into the
      next window, no degraded output).
    """
    known_ids: set[str] = set(snapshot.incident_ids)
    known_ids.update(inc.incident_id for inc in incidents)
    if snapshot.briefing_count == 0 and not known_ids:
        _log.debug("empty period (no briefings, no incidents): skipping narration")
        return None

    try:
        out = await structured_llm_call(
            model=LLM_MODEL_NARRATOR,
            system=_SYSTEM_PROMPT,
            user_content=_render_prompt(snapshot, incidents, period_end),
            output_model=NarrationOutput,
        )
    except LLMUnavailable as e:
        _log.warning(
            "narration skipped for window [%s, %s]: %s",
            snapshot.period_start,
            period_end,
            e,
        )
        return None

    text = out.text.strip()
    if len(text) > _TEXT_MAX:
        # Contract enforces max_length; truncate defensively before construction.
        text = text[:_TEXT_MAX]

    # Keep only ids we actually know about (window or KV), deduped in order:
    # a hallucinated id must never leak into the audit trail.
    referenced = [i for i in dict.fromkeys(out.incident_ids_referenced) if i in known_ids]

    return Narrative(
        period_start=snapshot.period_start,
        period_end=period_end,
        text=text,
        incident_ids_referenced=referenced,
    )


async def narrate_once(
    mesh: AgentMesh,
    window: NarratorWindow,
    *,
    now: float | None = None,
) -> Narrative | None:
    """One timer tick: drain the window, read incidents, compose, publish.

    The window is reset up front so a failed or skipped period never
    bleeds into the next one (spec: no retry into the next window).
    """
    period_end = time.time() if now is None else now
    snapshot = window.reset(period_end)

    incidents: list[IncidentState] = []
    try:
        entries = await mesh.kv.list_models(INCIDENT_WILDCARD, IncidentState)
        incidents = [e.value for e in entries if e.value is not None]
    except Exception as e:
        # A stale-schema key must not kill the narrator; narrate from the
        # window counters alone.
        _log.warning("incident KV read failed, narrating from window only: %s", e)

    narrative = await compose_narrative(snapshot, incidents, period_end=period_end)
    if narrative is None:
        return None

    try:
        await mesh.publish(NARRATIVE_SUBJECT, narrative)
        _log.info(
            "narrative published: %d chars, %d incident(s) referenced",
            len(narrative.text),
            len(narrative.incident_ids_referenced),
        )
    except Exception as e:
        _log.warning("narrative publish failed: %s", e)
    return narrative


async def _narrate_loop(mesh: AgentMesh, window: NarratorWindow) -> None:
    """Tick :func:`narrate_once` every ``NARRATOR_INTERVAL_S`` seconds."""
    try:
        while True:
            await asyncio.sleep(NARRATOR_INTERVAL_S)
            try:
                await narrate_once(mesh, window)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # pragma: no cover -- defensive guard
                _log.warning("narrate tick failed: %s", e)
    except asyncio.CancelledError:
        return


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------


def build_agent(mesh: AgentMesh, window: NarratorWindow) -> None:
    """Register the narrator agent on ``mesh`` against the shared ``window``.

    Split out (uav/fire-sim convention) so tests can register the handler
    without going through the ``__main__`` boot path. The handler only
    appends to the window; narration happens in :func:`_narrate_loop`.
    """

    @mesh.agent(
        AgentSpec(
            name="narrator",
            description=(
                "Background mission narrator: every 5 minutes it summarizes "
                "swarm activity across all incidents into one paragraph on "
                "mesh.swarm.narrative. Not invocable; do NOT use it to query "
                "incident state (read wildfire.incident.* instead)."
            ),
        ),
        sources=[
            mesh.subject_source(BRIEFING_SUBJECT_PATTERN),
            mesh.subject_source(STATS_SUBJECT),
        ],
    )
    async def narrator(msg: MeshMessage[bytes]) -> None:
        # Two sources share one handler; the MeshMessage envelope carries
        # the subject, so we validate per source here (the SDK cannot pick
        # a model per source on a shared handler).
        try:
            if msg.payload is None:
                return
            if msg.subject == STATS_SUBJECT:
                window.add_stats(SwarmStats.model_validate_json(msg.payload))
            elif msg.subject.startswith("mesh.briefing."):
                window.add_briefing(IncidentBriefing.model_validate_json(msg.payload))
        except Exception as e:
            # One malformed message does not kill the agent.
            _log.warning("narrator source message failed on %r: %s", msg.subject, e)


# ---------------------------------------------------------------------------
# Process entry point: `python -m demos.wildfire.fleet.narrator`
# ---------------------------------------------------------------------------


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    window = NarratorWindow()
    build_agent(mesh, window)

    # Mirror fire_sim: wire SIGTERM/SIGINT to a clean-shutdown event so the
    # orchestrator's terminate() unblocks the wait the same way Ctrl-C does.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop_event.set)

    async with mesh:
        window.period_start = time.time()  # window opens at connect, not import
        tick_task = asyncio.create_task(_narrate_loop(mesh, window))
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            tick_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tick_task


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
