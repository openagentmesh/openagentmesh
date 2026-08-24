"""Unit tests for the briefer LLM peer (km/specs/wildfire/briefer.md).

Covers the pure logic that must hold without NATS or an LLM:

  - `find_merge_target` clustering (radius + time window, boundaries)
  - `new_incident_id` shape ("inc-" + 8 hex chars)
  - `severity_from_max` heuristic boundaries
  - degraded briefing path (monkeypatched `structured_llm_call` raising
    `LLMUnavailable`)
  - briefing assembly from a stubbed LLM draft (facts come from the caller,
    judgement from the draft; model id from config, never hardcoded)
  - module source contract (kv_source on detections, subject_source on
    mesh.survey.>, mesh.publish on mesh.briefing.*, no aspirational kwargs,
    no hardcoded model id)

Plus ONE integration-lite test against `AgentMesh.local()`: a pending
detection put produces a durable IncidentState and stamps the agreed
incident id back onto the detection record.

LLM calls are always monkeypatched at the module attribute
(`briefer.structured_llm_call`); these tests never hit the network.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from pathlib import Path

import pytest

from demos.wildfire.core.config import LLM_MODEL_BRIEFER
from demos.wildfire.core.contracts import (
    Coords,
    DetectionRecord,
    IncidentBriefing,
    IncidentState,
    SurveyResult,
)
from demos.wildfire.core.keys import INCIDENT_PREFIX, detection_key
from demos.wildfire.core.llm import LLMUnavailable
from demos.wildfire.fleet import briefer
from openagentmesh import AgentMesh


def _detection(
    det_id: str,
    *,
    x: float = 0.0,
    y: float = 0.0,
    created_at: float = 1000.0,
    severity: float = 0.7,
    state: str = "pending",
    survey: SurveyResult | None = None,
) -> DetectionRecord:
    return DetectionRecord(
        detection_id=det_id,
        state=state,
        coords=Coords(x=x, y=y),
        severity=severity,
        detector_instance_id="uav-test",
        created_at=created_at,
        last_updated=created_at,
        survey=survey,
        incident_id=None,
    )


# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_build_agent_is_callable():
    assert callable(briefer.build_agent)


def test_main_is_async_coroutine_function():
    assert inspect.iscoroutinefunction(briefer._main)


# ---------------------------------------------------------------------------
# Correlation (pure)
# ---------------------------------------------------------------------------


def test_merge_within_radius_and_window():
    existing = _detection("d0", x=0.0, y=0.0, created_at=1000.0)
    incoming = _detection("d1", x=0.3, y=0.0, created_at=1030.0)  # 0.3 km, 30 s
    assert briefer.find_merge_target(incoming, {"inc-1": [existing]}) == "inc-1"


def test_no_merge_outside_radius():
    existing = _detection("d0", x=0.0, y=0.0, created_at=1000.0)
    incoming = _detection("d1", x=0.6, y=0.0, created_at=1000.0)  # 0.6 km > 0.5
    assert briefer.find_merge_target(incoming, {"inc-1": [existing]}) is None


def test_no_merge_outside_time_window():
    existing = _detection("d0", x=0.0, y=0.0, created_at=1000.0)
    incoming = _detection("d1", x=0.1, y=0.0, created_at=1061.0)  # 61 s > 60
    assert briefer.find_merge_target(incoming, {"inc-1": [existing]}) is None


def test_merge_boundary_exactly_at_radius_and_window():
    existing = _detection("d0", x=0.0, y=0.0, created_at=1000.0)
    incoming = _detection("d1", x=0.5, y=0.0, created_at=1060.0)  # == radius, == window
    assert briefer.find_merge_target(incoming, {"inc-1": [existing]}) == "inc-1"


def test_merge_picks_matching_incident_among_many():
    far = _detection("d0", x=4.0, y=4.0, created_at=1000.0)
    near = _detection("d1", x=-1.0, y=-1.0, created_at=1000.0)
    incoming = _detection("d2", x=-1.2, y=-1.0, created_at=1010.0)
    incidents = {"inc-far": [far], "inc-near": [near]}
    assert briefer.find_merge_target(incoming, incidents) == "inc-near"


def test_no_merge_against_empty_incidents():
    incoming = _detection("d1")
    assert briefer.find_merge_target(incoming, {}) is None


def test_new_incident_id_shape():
    iid = briefer.new_incident_id()
    assert iid.startswith("inc-")
    assert len(iid) == len("inc-") + 8
    int(iid[4:], 16)  # raises ValueError if not hex


# ---------------------------------------------------------------------------
# Severity heuristic (pure)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("max_severity", "expected"),
    [
        (0.0, "low"),
        (0.34, "low"),
        (0.35, "med"),
        (0.59, "med"),
        (0.6, "high"),
        (0.79, "high"),
        (0.8, "critical"),
        (1.0, "critical"),
    ],
)
def test_severity_from_max_boundaries(max_severity: float, expected: str):
    assert briefer.severity_from_max(max_severity) == expected


def test_severity_from_detections_uses_max():
    dets = [
        _detection("d0", severity=0.2),
        _detection("d1", severity=0.85),
        _detection("d2", severity=0.5),
    ]
    assert briefer.severity_from_detections(dets) == "critical"


def test_severity_from_detections_empty_is_low():
    assert briefer.severity_from_detections([]) == "low"


# ---------------------------------------------------------------------------
# Degraded briefing path (LLM unavailable)
# ---------------------------------------------------------------------------


async def test_compose_briefing_degrades_on_llm_unavailable(monkeypatch):
    async def boom(**kwargs):
        raise LLMUnavailable("no key")

    monkeypatch.setattr(briefer, "structured_llm_call", boom)

    survey = SurveyResult(
        surveyor_instance_id="drone-1",
        timestamp=1005.0,
        fire_visible=True,
        persons_detected=3,
        structures_visible=1,
    )
    dets = [_detection("d1", severity=0.9, state="surveyed", survey=survey)]
    b = await briefer.compose_briefing(
        incident_id="inc-deadbeef",
        detections=dets,
        issuing_instance_id="briefer-me",
        now=1234.5,
    )
    assert isinstance(b, IncidentBriefing)
    assert b.summary == "Briefing unavailable, see KV record"
    assert b.confidence == 0.0
    assert b.severity == "critical"  # 0.9 >= 0.8
    assert b.persons_estimated == 3
    assert b.structures_at_risk == 1
    assert "dispatch_medevac" in b.recommended_actions  # persons > 0
    assert b.sources == ["d1"]
    assert b.incident_id == "inc-deadbeef"
    assert b.issued_at == 1234.5
    assert b.issuing_instance_id == "briefer-me"


def test_degraded_actions_by_severity():
    assert briefer.degraded_actions("low", 0) == ["monitor"]
    assert briefer.degraded_actions("med", 0) == ["dispatch_ffunit"]
    assert briefer.degraded_actions("high", 0) == ["dispatch_heli", "dispatch_ffunit"]
    assert briefer.degraded_actions("critical", 0) == [
        "dispatch_heli",
        "dispatch_ffunit",
        "evacuate",
    ]
    assert "dispatch_medevac" in briefer.degraded_actions("low", 2)


# ---------------------------------------------------------------------------
# Briefing assembly from a stubbed LLM draft
# ---------------------------------------------------------------------------


async def test_compose_briefing_assembles_facts_around_llm_draft(monkeypatch):
    calls: dict = {}

    async def stub(**kwargs):
        calls.update(kwargs)
        return briefer.BriefingDraft(
            severity="high",
            summary="Fire spreading north; two structures within 300 m.",
            persons_estimated=2,
            structures_at_risk=2,
            recommended_actions=["dispatch_heli", "dispatch_medevac"],
            confidence=0.85,
        )

    monkeypatch.setattr(briefer, "structured_llm_call", stub)

    dets = [_detection("d1"), _detection("d2", x=0.1)]
    b = await briefer.compose_briefing(
        incident_id="inc-abc12345",
        detections=dets,
        issuing_instance_id="briefer-me",
        now=999.0,
    )

    # Facts are ours, never the LLM's.
    assert b.incident_id == "inc-abc12345"
    assert b.sources == ["d1", "d2"]
    assert b.issued_at == 999.0
    assert b.issuing_instance_id == "briefer-me"
    # Judgement comes from the draft.
    assert b.severity == "high"
    assert b.persons_estimated == 2
    assert b.recommended_actions == ["dispatch_heli", "dispatch_medevac"]
    assert b.confidence == 0.85

    # The call went through the shared helper with the config model id...
    assert calls["model"] == LLM_MODEL_BRIEFER
    assert calls["output_model"] is briefer.BriefingDraft
    # ...and the prompt is structured data only (valid JSON with the records).
    payload = json.loads(calls["user_content"])
    assert payload["incident_id"] == "inc-abc12345"
    assert [d["detection_id"] for d in payload["detections"]] == ["d1", "d2"]


# ---------------------------------------------------------------------------
# Source contract: module text invariants (mirrors test_uav.py)
# ---------------------------------------------------------------------------


_BRIEFER_PATH = Path(briefer.__file__)
_BRIEFER_SRC = _BRIEFER_PATH.read_text()


def test_briefer_module_uses_kv_source_on_detections():
    assert "kv_source" in _BRIEFER_SRC
    assert "wildfire.detection" in _BRIEFER_SRC


def test_briefer_module_uses_subject_source_on_surveys():
    assert 'mesh.subject_source("mesh.survey.>")' in _BRIEFER_SRC


def test_briefer_module_publishes_briefings():
    assert "mesh.publish" in _BRIEFER_SRC
    assert "mesh.briefing." in _BRIEFER_SRC


def test_briefer_module_gates_ticks_with_cas():
    # The queue-group-equivalent gate is try_cas_model on last_briefing_at;
    # kv_source(queue_group=...) raises NotImplementedError in v1.
    assert "try_cas_model" in _BRIEFER_SRC
    assert "queue_group=" not in _BRIEFER_SRC


@pytest.mark.parametrize("needle", ["bucket=", "prefix="])
def test_briefer_module_does_not_use_aspirational_kwargs(needle: str):
    # A-09 / single-bucket pivot: no bucket=/prefix= kwargs exist in the SDK.
    assert needle not in _BRIEFER_SRC, f"{needle!r} is not a real SDK kwarg"


def test_briefer_module_never_hardcodes_a_model_id():
    assert "claude-" not in _BRIEFER_SRC, "model id must come from config.LLM_MODEL_BRIEFER"
    assert "LLM_MODEL_BRIEFER" in _BRIEFER_SRC


def test_briefer_module_routes_llm_calls_through_shared_helper():
    assert "structured_llm_call" in _BRIEFER_SRC
    assert "AsyncOpenAI" not in _BRIEFER_SRC
    assert "import openai" not in _BRIEFER_SRC
    assert "AsyncAnthropic" not in _BRIEFER_SRC
    assert "import anthropic" not in _BRIEFER_SRC


# ---------------------------------------------------------------------------
# Integration-lite: detection put -> incident appears in KV (AgentMesh.local)
# ---------------------------------------------------------------------------

# NATS wildcard suffix — bare prefixes return [] per _context.py list().
INCIDENT_WILDCARD = f"{INCIDENT_PREFIX}.*"


async def test_detection_put_creates_incident_in_kv():
    """A pending DetectionRecord put produces a durable IncidentState whose
    detection_ids contains the detection, and the agreed incident id is
    CAS-stamped back onto the detection record.

    No tick loop runs (build_agent does not start it), so no briefing and no
    LLM call happens here.
    """
    async with AgentMesh.local() as mesh:
        briefer.build_agent(mesh)
        # Source binding is deferred until catalog()/call() per
        # _subscribe_pending; trigger it explicitly so the kv_source fires.
        await mesh.catalog()
        await asyncio.sleep(0.5)

        rec = _detection("feedc0de00000001", created_at=time.time())
        await mesh.kv.put_model(detection_key(rec.detection_id), rec)

        incidents: list[IncidentState] = []
        for _ in range(30):
            await asyncio.sleep(0.1)
            raw = [e for e in await mesh.kv.list(INCIDENT_WILDCARD) if e.value]
            if raw:
                incidents = [IncidentState.model_validate_json(e.value) for e in raw]
                break

        assert len(incidents) == 1, f"expected exactly 1 incident, got {len(incidents)}"
        st = incidents[0]
        assert st.incident_id.startswith("inc-")
        assert st.detection_ids == [rec.detection_id]
        assert st.resolved is False
        assert st.briefings == []
        assert st.last_briefing_at == 0.0  # never briefed -> due at first tick

        # The agreement CAS stamped the incident id onto the detection record.
        updated = await mesh.kv.get_model(detection_key(rec.detection_id), DetectionRecord)
        assert updated.incident_id == st.incident_id
