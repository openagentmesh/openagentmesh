"""Unit tests for the tasker LLM peer (km/specs/wildfire/tasker.md).

Conventions mirror test_heli.py: module-shape assertions, source-text
invariants, then live boot tests against ``AgentMesh.local()``.

Asserted invariants:

  - Handler returns a valid ``TaskCommand`` with a stubbed
    ``structured_llm_call`` (no network in unit tests; the module attribute
    is monkeypatched).
  - The stub receives grounding content containing the operator text, the
    open incidents (resolved incidents excluded, detection centroid joined
    in), and the available fleets.
  - ``LLMUnavailable`` surfaces as a ``MeshError`` with code
    ``llm_unavailable`` whose message says the translation service is
    unavailable.
  - Live round trip: ``mesh.call("tasker", TaskTranslateRequest(...))``
    returns the stubbed command through the real dispatch path, and the
    degraded path arrives at the caller as a clean typed error, not a
    timeout.
"""
from __future__ import annotations

import inspect
import json
import time
from pathlib import Path

import pytest

from demos.wildfire.core.config import LLM_MODEL_TASKER
from demos.wildfire.core.contracts import (
    Coords,
    DetectionRecord,
    IncidentState,
    TaskCommand,
    TaskTranslateRequest,
)
from demos.wildfire.core.keys import (
    DETECTION_PREFIX,
    INCIDENT_PREFIX,
    detection_key,
    incident_key,
)
from demos.wildfire.core.llm import LLMUnavailable
from openagentmesh import AgentMesh, CatalogEntry, KVEntry, MeshError

tasker = pytest.importorskip(
    "demos.wildfire.fleet.tasker",
    reason="demos.wildfire.fleet.tasker not yet on disk.",
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _make_request(text: str = "drop water on the ridge fire") -> TaskTranslateRequest:
    return TaskTranslateRequest(operator_id="op-7", text=text)


def _make_incident(
    incident_id: str,
    *,
    detection_ids: list[str] | None = None,
    resolved: bool = False,
) -> IncidentState:
    return IncidentState(
        incident_id=incident_id,
        detection_ids=detection_ids if detection_ids is not None else ["det-1"],
        last_briefing_at=time.time(),
        briefings=[],
        severity="high",
        resolved=resolved,
        resolved_at=time.time() if resolved else None,
    )


def _make_detection(detection_id: str, x: float, y: float) -> DetectionRecord:
    now = time.time()
    return DetectionRecord(
        detection_id=detection_id,
        state="surveyed",
        coords=Coords(x=x, y=y),
        severity=0.8,
        detector_instance_id="uav-1",
        created_at=now,
        last_updated=now,
    )


def _make_command() -> TaskCommand:
    return TaskCommand(
        target_fleet="heli",
        coords=Coords(x=1.0, y=2.0),
        incident_id=None,
        priority="high",
        persons_estimated=0,
        rationale="Operator asked for an aerial water drop on the ridge.",
    )


def _entry(key: str, model) -> KVEntry:
    return KVEntry(
        key=key,
        value=model.model_dump_json().encode(),
        revision=1,
        operation="PUT",
    )


def _stub_llm(result: TaskCommand | None, captured: dict, *, exc: Exception | None = None):
    """Stand-in for structured_llm_call: records kwargs, returns or raises."""

    async def stub(**kwargs):
        captured.update(kwargs)
        if exc is not None:
            raise exc
        return result

    return stub


# ---------------------------------------------------------------------------
# Fake mesh (unit tests never hit the network)
# ---------------------------------------------------------------------------


class _FakeKV:
    def __init__(self, entries_by_prefix: dict[str, list[KVEntry]]):
        self._by_prefix = entries_by_prefix
        self.requested: list[str] = []

    async def list(self, pattern: str) -> list[KVEntry]:
        self.requested.append(pattern)
        for prefix, entries in self._by_prefix.items():
            if pattern.startswith(prefix):
                return list(entries)
        return []


class _FakeMesh:
    def __init__(
        self,
        *,
        incidents: tuple[IncidentState, ...] = (),
        detections: tuple[DetectionRecord, ...] = (),
        catalog: tuple[CatalogEntry, ...] = (),
    ):
        self.kv = _FakeKV(
            {
                INCIDENT_PREFIX: [
                    _entry(incident_key(i.incident_id), i) for i in incidents
                ],
                DETECTION_PREFIX: [
                    _entry(detection_key(d.detection_id), d) for d in detections
                ],
            }
        )
        self._catalog = list(catalog)

    async def catalog(self) -> list[CatalogEntry]:
        return list(self._catalog)


# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_module_exposes_build_agent_translate_and_main():
    assert callable(tasker.build_agent)
    assert inspect.iscoroutinefunction(tasker.translate)
    assert inspect.iscoroutinefunction(tasker._main)


_TASKER_PATH = Path(tasker.__file__)


def test_module_registers_tasker_agent_spec():
    text = _TASKER_PATH.read_text()
    assert 'name=AGENT_NAME' in text or 'name="tasker"' in text
    assert tasker.AGENT_NAME == "tasker"


def test_module_takes_model_id_from_config():
    """Model id comes from config, never hardcoded (hard constraint)."""
    text = _TASKER_PATH.read_text()
    assert "LLM_MODEL_TASKER" in text
    assert "claude-" not in text


@pytest.mark.parametrize(
    "needle",
    [
        "bucket=",  # no bucket kwarg exists (A-09, single-bucket pivot)
        "AsyncOpenAI",  # all LLM calls go through structured_llm_call
        "import openai",
        "AsyncAnthropic",  # no direct-Anthropic leftovers either
        "import anthropic",
        "put_model(",  # request/reply only: no KV writes
        "kv.put(",
        ".publish(",  # no publishing
    ],
)
def test_module_does_not_reference_forbidden_artefacts(needle: str):
    text = _TASKER_PATH.read_text()
    assert needle not in text, f"{needle!r} should not appear in {_TASKER_PATH.name}"


def test_description_written_for_tool_selection():
    """Description states what it does, inputs, and when NOT to use it."""
    desc = tasker.AGENT_DESCRIPTION
    assert "TaskCommand" in desc
    assert "TaskTranslateRequest" in desc
    assert "NOT" in desc


# ---------------------------------------------------------------------------
# translate(): stubbed LLM, fake mesh
# ---------------------------------------------------------------------------


async def test_translate_returns_stubbed_taskcommand(monkeypatch):
    expected = _make_command()
    captured: dict = {}
    monkeypatch.setattr(tasker, "structured_llm_call", _stub_llm(expected, captured))

    result = await tasker.translate(_FakeMesh(), _make_request())

    assert result is expected
    assert captured["model"] == LLM_MODEL_TASKER
    assert captured["output_model"] is TaskCommand
    assert captured["system"] == tasker.SYSTEM_PROMPT


async def test_grounding_contains_operator_text_incidents_and_fleets(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(tasker, "structured_llm_call", _stub_llm(_make_command(), captured))

    mesh = _FakeMesh(
        incidents=(
            _make_incident("inc-open-1", detection_ids=["d1", "d2"]),
            _make_incident("inc-closed-1", resolved=True),
        ),
        detections=(
            _make_detection("d1", 1.0, 1.0),
            _make_detection("d2", 3.0, 3.0),
        ),
        catalog=(
            CatalogEntry(name="low-alt.heli", description="water bomber"),
            CatalogEntry(name="ground.medevac", description="extraction"),
            CatalogEntry(name="tasker", description="translator"),
        ),
    )
    req = _make_request()
    await tasker.translate(mesh, req)

    payload = json.loads(captured["user_content"])
    assert payload["text"] == req.text
    assert payload["operator_id"] == req.operator_id

    incidents = {i["incident_id"]: i for i in payload["open_incidents"]}
    assert "inc-open-1" in incidents
    assert "inc-closed-1" not in incidents, "resolved incidents must be excluded"
    open_inc = incidents["inc-open-1"]
    assert open_inc["severity"] == "high"
    assert open_inc["coords"] == {"x": 2.0, "y": 2.0}, "centroid of d1+d2"

    # Only catalog-present action fleets, projected to short names.
    assert payload["available_fleets"] == ["heli", "medevac"]


async def test_grounding_falls_back_to_full_fleet_set_on_empty_catalog(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(tasker, "structured_llm_call", _stub_llm(_make_command(), captured))

    await tasker.translate(_FakeMesh(), _make_request())

    payload = json.loads(captured["user_content"])
    assert set(payload["available_fleets"]) == {"heli", "ffunit", "medevac"}
    assert payload["open_incidents"] == []


async def test_llm_unavailable_raises_mesh_error_with_recoverable_code(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        tasker,
        "structured_llm_call",
        _stub_llm(None, captured, exc=LLMUnavailable("OPENROUTER_API_KEY not set")),
    )

    with pytest.raises(MeshError) as excinfo:
        await tasker.translate(_FakeMesh(), _make_request())

    err = excinfo.value
    assert err.code == tasker.LLM_UNAVAILABLE_CODE == "llm_unavailable"
    assert "unavailable" in err.message.lower()
    assert err.agent == "tasker"


# ---------------------------------------------------------------------------
# Live boot tests against AgentMesh.local()
# ---------------------------------------------------------------------------


async def test_tasker_call_round_trips_with_stubbed_llm(monkeypatch):
    """mesh.call("tasker", TaskTranslateRequest(...)) round-trips the stub."""
    expected = _make_command()
    captured: dict = {}
    monkeypatch.setattr(tasker, "structured_llm_call", _stub_llm(expected, captured))

    async with AgentMesh.local() as mesh:
        tasker.build_agent(mesh)
        # Seed one open incident so the live KV grounding path is exercised.
        await mesh.kv.put(
            incident_key("inc-live-1"),
            _make_incident("inc-live-1").model_dump_json(),
        )

        req = _make_request()
        result = await mesh.call("tasker", req, timeout=10.0)

    command = TaskCommand.model_validate(result)
    assert command == expected

    payload = json.loads(captured["user_content"])
    assert payload["text"] == req.text
    assert "inc-live-1" in {i["incident_id"] for i in payload["open_incidents"]}


async def test_tasker_call_surfaces_llm_unavailable_as_typed_error(monkeypatch):
    """Degraded path reaches the caller as a clean MeshError, not a timeout."""
    monkeypatch.setattr(
        tasker,
        "structured_llm_call",
        _stub_llm(None, {}, exc=LLMUnavailable("rate limited")),
    )

    async with AgentMesh.local() as mesh:
        tasker.build_agent(mesh)

        t0 = time.monotonic()
        with pytest.raises(MeshError) as excinfo:
            await mesh.call("tasker", _make_request(), timeout=10.0)
        elapsed = time.monotonic() - t0

    err = excinfo.value
    assert err.code == "llm_unavailable"
    assert "unavailable" in err.message.lower()
    assert err.agent == "tasker"
    assert elapsed < 5.0, "error must be a reply, not a timeout"
