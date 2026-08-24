"""Unit tests for the narrator LLM peer (km/specs/wildfire/narrator.md).

Network-free by construction: the LLM step is exercised by monkeypatching
``narrator.structured_llm_call`` (the module-global the compose step calls),
and the publish/KV surface is a hand-rolled FakeMesh. No AgentMesh.local(),
no NATS, no Anthropic API.

Covers:

  - Module shape + source-text invariants (house style: name="narrator",
    subject sources, no kv_source, no bucket= kwarg, config-driven model id).
  - ``NarratorWindow`` accumulation + reset semantics.
  - ``compose_narrative``: valid stub -> assembled ``Narrative`` (facts
    period_start/period_end from the window, text truncation to the frozen
    contract cap, hallucinated incident ids filtered out).
  - ``LLMUnavailable`` -> None (skip the period, no degraded output).
  - Empty period (no briefings, no incidents) -> no LLM call at all;
    stats-only windows count as silence too.
  - ``narrate_once``: publishes on mesh.swarm.narrative via mesh.publish,
    resets the window even when the LLM fails (no retry into next period).
"""
from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import Any

import pytest

from demos.wildfire.core.config import LLM_MODEL_NARRATOR
from demos.wildfire.core.contracts import (
    IncidentBriefing,
    IncidentState,
    Narrative,
    SwarmStats,
)
from demos.wildfire.core.keys import INCIDENT_PREFIX, incident_key
from demos.wildfire.core.llm import LLMUnavailable
from openagentmesh import KVEntry

narrator = pytest.importorskip(
    "demos.wildfire.fleet.narrator",
    reason="demos.wildfire.fleet.narrator not yet on disk.",
)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _briefing(incident_id: str = "inc-1", **overrides) -> IncidentBriefing:
    defaults: dict[str, Any] = dict(
        incident_id=incident_id,
        severity="high",
        summary=f"Fire at {incident_id}: growing, two structures at risk.",
        persons_estimated=2,
        structures_at_risk=2,
        recommended_actions=["dispatch_heli"],
        sources=["det-1"],
        issued_at=time.time(),
        issuing_instance_id="briefer-1",
    )
    defaults.update(overrides)
    return IncidentBriefing(**defaults)


def _stats(**overrides) -> SwarmStats:
    defaults: dict[str, Any] = dict(
        timestamp=time.time(),
        uavs_active=1,
        uavs_total=1,
        drones_active=4,
        drones_total=5,
        helis_active=1,
        helis_total=1,
        ffunits_active=3,
        ffunits_total=3,
        medevacs_active=2,
        medevacs_total=3,
        incidents_open=1,
        incidents_resolved=0,
        fires_detected_total=3,
        persons_recovered_total=1,
    )
    defaults.update(overrides)
    return SwarmStats(**defaults)


def _incident(incident_id: str = "inc-1", **overrides) -> IncidentState:
    defaults: dict[str, Any] = dict(
        incident_id=incident_id,
        detection_ids=["det-1"],
        last_briefing_at=time.time(),
        briefings=[_briefing(incident_id)],
        severity="high",
        resolved=False,
    )
    defaults.update(overrides)
    return IncidentState(**defaults)


def _snapshot(
    *,
    period_start: float = 1000.0,
    briefing_count: int = 0,
    incident_ids: list[str] | None = None,
    latest_stats: SwarmStats | None = None,
) -> narrator.WindowSnapshot:
    return narrator.WindowSnapshot(
        period_start=period_start,
        briefing_count=briefing_count,
        incident_ids=incident_ids or [],
        latest_stats=latest_stats,
    )


def _stub_llm(monkeypatch, *, result=None, exc=None):
    """Monkeypatch narrator.structured_llm_call; returns the call log."""
    calls: list[dict] = []

    async def stub(*, model, system, user_content, output_model, **kwargs):
        calls.append(
            dict(
                model=model,
                system=system,
                user_content=user_content,
                output_model=output_model,
            )
        )
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(narrator, "structured_llm_call", stub)
    return calls


class _FakeKV:
    def __init__(self, entries: list[KVEntry]) -> None:
        self.entries = entries
        self.list_calls: list[tuple[str, type]] = []

    async def list_models(self, prefix: str, model_cls: type) -> list[KVEntry]:
        self.list_calls.append((prefix, model_cls))
        return self.entries


class _FakeMesh:
    """Just enough surface for narrate_once: kv.list_models + publish."""

    def __init__(self, incidents: list[IncidentState] | None = None) -> None:
        entries = [
            KVEntry(
                key=incident_key(inc.incident_id),
                value=inc,
                revision=1,
                operation="PUT",
            )
            for inc in (incidents or [])
        ]
        self.kv = _FakeKV(entries)
        self.published: list[tuple[str, object]] = []

    async def publish(self, subject: str, payload) -> None:
        self.published.append((subject, payload))


# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_build_agent_is_callable():
    assert callable(narrator.build_agent)


def test_main_is_async_coroutine_function():
    assert inspect.iscoroutinefunction(narrator._main)


def test_subjects_match_spec():
    assert narrator.BRIEFING_SUBJECT_PATTERN == "mesh.briefing.>"
    assert narrator.STATS_SUBJECT == "mesh.swarm.stats"
    assert narrator.NARRATIVE_SUBJECT == "mesh.swarm.narrative"
    # kv.list wildcard rule: bare prefixes return [].
    assert f"{INCIDENT_PREFIX}.>" == narrator.INCIDENT_WILDCARD


def test_text_cap_mirrors_frozen_contract():
    # _TEXT_MAX is derived from Narrative.text's max_length, not hardcoded.
    assert narrator._TEXT_MAX == 1000


# ---------------------------------------------------------------------------
# Source-text invariants (house style)
# ---------------------------------------------------------------------------


_NARRATOR_PATH = Path(narrator.__file__)


def test_narrator_module_registers_narrator_agent_spec():
    text = _NARRATOR_PATH.read_text()
    assert 'name="narrator"' in text


def test_narrator_module_uses_subject_sources_not_kv_source():
    text = _NARRATOR_PATH.read_text()
    assert "subject_source(" in text
    assert "kv_source(" not in text


def test_narrator_module_uses_config_constants():
    text = _NARRATOR_PATH.read_text()
    assert "LLM_MODEL_NARRATOR" in text
    assert "NARRATOR_INTERVAL_S" in text
    # Model id must come from config, never inlined.
    assert "claude-haiku" not in text


def test_narrator_module_routes_llm_through_shared_helper():
    text = _NARRATOR_PATH.read_text()
    assert "structured_llm_call" in text
    assert "LLMUnavailable" in text
    assert "AsyncAnthropic" not in text  # no direct client


def test_narrator_module_does_not_use_bucket_kwarg():
    # Single mesh-context bucket; the SDK has no bucket= parameter (A-09).
    text = _NARRATOR_PATH.read_text()
    assert "bucket=" not in text


# ---------------------------------------------------------------------------
# Window accumulation
# ---------------------------------------------------------------------------


def test_window_accumulates_briefings_and_incident_ids():
    w = narrator.NarratorWindow(period_start=100.0)
    w.add_briefing(_briefing("inc-1"))
    w.add_briefing(_briefing("inc-2"))
    w.add_briefing(_briefing("inc-1"))  # duplicate incident, third briefing
    assert w.briefing_count == 3
    assert w.incident_ids == {"inc-1", "inc-2"}


def test_window_keeps_latest_stats_only():
    w = narrator.NarratorWindow(period_start=100.0)
    w.add_stats(_stats(fires_detected_total=1))
    w.add_stats(_stats(fires_detected_total=7))
    assert w.latest_stats is not None
    assert w.latest_stats.fires_detected_total == 7


def test_window_reset_returns_snapshot_and_clears():
    w = narrator.NarratorWindow(period_start=100.0)
    w.add_briefing(_briefing("inc-2"))
    w.add_briefing(_briefing("inc-1"))
    w.add_stats(_stats())

    snap = w.reset(now=400.0)

    # Snapshot carries the drained period.
    assert snap.period_start == 100.0
    assert snap.briefing_count == 2
    assert snap.incident_ids == ["inc-1", "inc-2"]  # sorted, deduped
    assert snap.latest_stats is not None

    # Window restarts fresh at `now`.
    assert w.period_start == 400.0
    assert w.briefing_count == 0
    assert w.incident_ids == set()
    assert w.latest_stats is None


# ---------------------------------------------------------------------------
# compose_narrative: the narrate step
# ---------------------------------------------------------------------------


async def test_compose_narrative_valid_stub_returns_narrative(monkeypatch):
    calls = _stub_llm(
        monkeypatch,
        result=narrator.NarrationOutput(
            text="Incident inc-1 flared up; a heli was dispatched.",
            incident_ids_referenced=["inc-1"],
        ),
    )
    snap = _snapshot(
        period_start=1000.0,
        briefing_count=2,
        incident_ids=["inc-1"],
        latest_stats=_stats(),
    )
    result = await narrator.compose_narrative(
        snap, [_incident("inc-1")], period_end=1300.0
    )

    assert isinstance(result, Narrative)
    assert result.period_start == 1000.0
    assert result.period_end == 1300.0
    assert result.text == "Incident inc-1 flared up; a heli was dispatched."
    assert result.incident_ids_referenced == ["inc-1"]

    # Exactly ONE structured call, wired per config + internal output model.
    assert len(calls) == 1
    assert calls[0]["model"] == LLM_MODEL_NARRATOR
    assert calls[0]["output_model"] is narrator.NarrationOutput
    # Prompt carries the KV incident summary + window counters.
    assert "inc-1" in calls[0]["user_content"]
    assert "Briefings received this window: 2" in calls[0]["user_content"]


async def test_compose_narrative_truncates_overlong_text(monkeypatch):
    _stub_llm(
        monkeypatch,
        result=narrator.NarrationOutput(text="x" * 1500, incident_ids_referenced=[]),
    )
    snap = _snapshot(briefing_count=1, incident_ids=["inc-1"])
    result = await narrator.compose_narrative(snap, [], period_end=1300.0)
    assert result is not None
    assert len(result.text) == narrator._TEXT_MAX  # contract max_length holds


async def test_compose_narrative_filters_hallucinated_incident_ids(monkeypatch):
    _stub_llm(
        monkeypatch,
        result=narrator.NarrationOutput(
            text="Summary.",
            incident_ids_referenced=["inc-1", "inc-ghost", "inc-1"],
        ),
    )
    snap = _snapshot(briefing_count=1, incident_ids=["inc-1"])
    result = await narrator.compose_narrative(snap, [], period_end=1300.0)
    assert result is not None
    # Unknown ids dropped, duplicates collapsed, order preserved.
    assert result.incident_ids_referenced == ["inc-1"]


async def test_compose_narrative_llm_unavailable_skips_period(monkeypatch):
    calls = _stub_llm(monkeypatch, exc=LLMUnavailable("no key"))
    snap = _snapshot(briefing_count=3, incident_ids=["inc-1"])
    result = await narrator.compose_narrative(
        snap, [_incident("inc-1")], period_end=1300.0
    )
    assert result is None  # skip: no degraded output
    assert len(calls) == 1  # it did try once (helper owns the retry)


async def test_compose_narrative_empty_period_makes_no_llm_call(monkeypatch):
    calls = _stub_llm(monkeypatch, exc=AssertionError("LLM must not be called"))
    result = await narrator.compose_narrative(
        _snapshot(), [], period_end=1300.0
    )
    assert result is None
    assert calls == []  # silence is not narrated


async def test_compose_narrative_stats_only_window_is_still_silence(monkeypatch):
    # Stats tick every 10 s regardless of activity: they alone never
    # justify a narration.
    calls = _stub_llm(monkeypatch, exc=AssertionError("LLM must not be called"))
    snap = _snapshot(latest_stats=_stats())
    result = await narrator.compose_narrative(snap, [], period_end=1300.0)
    assert result is None
    assert calls == []


async def test_compose_narrative_kv_incidents_alone_trigger_narration(monkeypatch):
    # A quiet window over a still-open incident is worth narrating.
    _stub_llm(
        monkeypatch,
        result=narrator.NarrationOutput(
            text="inc-1 still burning.", incident_ids_referenced=["inc-1"]
        ),
    )
    result = await narrator.compose_narrative(
        _snapshot(), [_incident("inc-1")], period_end=1300.0
    )
    assert result is not None
    assert result.incident_ids_referenced == ["inc-1"]


# ---------------------------------------------------------------------------
# narrate_once: tick body against a fake mesh
# ---------------------------------------------------------------------------


async def test_narrate_once_publishes_narrative_on_swarm_subject(monkeypatch):
    _stub_llm(
        monkeypatch,
        result=narrator.NarrationOutput(
            text="One incident handled.", incident_ids_referenced=["inc-1"]
        ),
    )
    mesh = _FakeMesh(incidents=[_incident("inc-1")])
    window = narrator.NarratorWindow(period_start=1000.0)
    window.add_briefing(_briefing("inc-1"))

    result = await narrator.narrate_once(mesh, window, now=1300.0)

    assert isinstance(result, Narrative)
    assert len(mesh.published) == 1
    subject, payload = mesh.published[0]
    assert subject == "mesh.swarm.narrative"
    assert isinstance(payload, Narrative)
    assert payload.period_start == 1000.0
    assert payload.period_end == 1300.0
    # KV read went through list_models on the incident wildcard.
    assert mesh.kv.list_calls == [(narrator.INCIDENT_WILDCARD, IncidentState)]
    # Window restarted for the next period.
    assert window.period_start == 1300.0
    assert window.briefing_count == 0


async def test_narrate_once_llm_failure_no_publish_window_still_reset(monkeypatch):
    _stub_llm(monkeypatch, exc=LLMUnavailable("rate limited"))
    mesh = _FakeMesh(incidents=[_incident("inc-1")])
    window = narrator.NarratorWindow(period_start=1000.0)
    window.add_briefing(_briefing("inc-1"))

    result = await narrator.narrate_once(mesh, window, now=1300.0)

    assert result is None
    assert mesh.published == []
    # Spec: skip the window, do NOT retry into the next period -- the
    # failed period's events are gone.
    assert window.briefing_count == 0
    assert window.period_start == 1300.0


async def test_narrate_once_empty_period_no_llm_call_no_publish(monkeypatch):
    calls = _stub_llm(monkeypatch, exc=AssertionError("LLM must not be called"))
    mesh = _FakeMesh()  # no incidents in KV
    window = narrator.NarratorWindow(period_start=1000.0)  # nothing seen

    result = await narrator.narrate_once(mesh, window, now=1300.0)

    assert result is None
    assert calls == []
    assert mesh.published == []
