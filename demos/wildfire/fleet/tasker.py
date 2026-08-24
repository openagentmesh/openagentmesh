"""tasker: LLM peer translating operator natural language into a TaskCommand.

Spec: ``km/specs/wildfire/tasker.md``. Plain Responder, single instance v1:
``mesh.call("tasker", TaskTranslateRequest)`` returns a ``TaskCommand``
synchronously. The tasker never executes commands, never writes KV, never
publishes: request/reply only. The operator (or the ``--auto-accept`` CLI)
owns execution of the returned command.

Grounding per request (structured data only, never raw text from other
agents):

  - Open incidents from ``wildfire.incident.*`` (KV read). ``IncidentState``
    carries no coords, so detection records are joined in to give each
    incident a centroid the LLM can target.
  - Available action fleets from the live catalog, constrained to the
    ``TaskCommand.target_fleet`` literal set (heli / ffunit / medevac).

Latency target <2s p95 => exactly ONE ``structured_llm_call`` per request,
no chains. Pydantic validation of ``TaskCommand`` (inside the shared helper)
is the safety net: a hallucinated ``target_fleet="hovercraft"`` fails
validation and surfaces as ``LLMUnavailable``.

Error path: ``LLMUnavailable`` is re-raised as a ``MeshError`` with the
recoverable code ``llm_unavailable``. The SDK's handler dispatch re-raises
``MeshError`` subclasses untouched and serializes them onto the error reply,
so the caller of ``mesh.call("tasker", ...)`` gets a clean typed error (not
a timeout) whose message says the translation service is unavailable.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os

from pydantic import ValidationError

from demos.wildfire.core.config import LLM_MODEL_TASKER
from demos.wildfire.core.contracts import (
    Coords,
    DetectionRecord,
    IncidentState,
    TaskCommand,
    TaskTranslateRequest,
)
from demos.wildfire.core.keys import DETECTION_PREFIX, INCIDENT_PREFIX
from demos.wildfire.core.llm import LLMUnavailable, structured_llm_call
from openagentmesh import AgentMesh, AgentSpec, CatalogEntry, MeshError

_log = logging.getLogger("wildfire.tasker")

AGENT_NAME = "tasker"

# Wire code for the degraded path. Unknown codes deserialize caller-side as a
# plain MeshError carrying this code (see openagentmesh._errors.from_envelope),
# so the CLI can catch MeshError, print, and re-prompt.
LLM_UNAVAILABLE_CODE = "llm_unavailable"

# The action-fleet short names TaskCommand.target_fleet accepts. The CLI maps
# these to channel-prefixed agent names (low-alt.heli, ground.ffunit,
# ground.medevac).
ACTION_FLEETS: tuple[str, ...] = ("heli", "ffunit", "medevac")

# Written for LLM tool selection: what it does, inputs, when NOT to use it.
AGENT_DESCRIPTION = (
    "Translates a firefighter operator's natural-language request into one "
    "typed TaskCommand (target_fleet: heli|ffunit|medevac, coords, priority, "
    "persons_estimated, rationale), grounded in the open incidents and the "
    "live agent catalog. Input: TaskTranslateRequest {operator_id, text}. "
    "Output: TaskCommand. Do NOT use it to execute or dispatch anything: it "
    "only translates; the operator sends the returned command to the fleet."
)

SYSTEM_PROMPT = """\
You translate a firefighter operator's natural-language request into exactly
one TaskCommand for the wildfire response mesh.

Translation rules:
- target_fleet must be one of: heli (aerial water drops), ffunit (ground fire
  suppression), medevac (person extraction). Pick the single best fit from
  the available_fleets list in the user message.
- coords are km from HQ at the origin; each axis must stay within
  [-5.0, 5.0]. When the operator refers to an open incident, use that
  incident's coords from the user message.
- priority is "low", "med", or "high"; infer it from the operator's urgency
  and the incident severity. Default to "med" when unclear.
- persons_estimated is only meaningful for medevac (people to extract);
  set 0 for heli and ffunit.
- incident_id: set it only when the request clearly refers to one of the
  provided open incidents; otherwise null.
- rationale: one short sentence explaining the translation, for the audit
  log.
Never invent fleets, incidents, or coordinates beyond the provided data.
"""


# ---------------------------------------------------------------------------
# Grounding: KV reads + catalog, projected to compact JSON for the LLM
# ---------------------------------------------------------------------------


async def _list_live_models(mesh: AgentMesh, prefix: str, model_cls):
    """Snapshot ``{prefix}.>`` and validate live PUT entries to ``model_cls``.

    Raw ``mesh.kv.list`` is used instead of ``list_models`` because the
    snapshot can surface DELETE tombstones (empty bytes) and stale-schema
    keys from previous runs; both are skipped instead of failing the request.
    """
    out = []
    for entry in await mesh.kv.list(f"{prefix}.>"):
        if entry.operation != "PUT" or not entry.value:
            continue
        try:
            out.append(model_cls.model_validate_json(entry.value))
        except ValidationError:
            _log.warning("skipping invalid %s at %s", model_cls.__name__, entry.key)
    return out


def _available_fleets(entries: list[CatalogEntry]) -> list[str]:
    """Project catalog entries to the action-fleet short-name set.

    Matches ``low-alt.heli`` / ``ground.ffunit`` / ``ground.medevac`` style
    names by their last dotted segment. Falls back to the full literal set
    when no action fleet is registered (e.g. bare test meshes), so the LLM
    is always constrained to valid ``target_fleet`` values.
    """
    present = {
        short
        for entry in entries
        for short in ACTION_FLEETS
        if entry.name == short or entry.name.endswith(f".{short}")
    }
    return sorted(present) if present else list(ACTION_FLEETS)


def _incident_summary(inc: IncidentState, det_coords: dict[str, Coords]) -> dict:
    """One compact grounding row per open incident (id, severity, coords)."""
    points = [det_coords[d] for d in inc.detection_ids if d in det_coords]
    coords = None
    if points:
        coords = {
            "x": round(sum(p.x for p in points) / len(points), 2),
            "y": round(sum(p.y for p in points) / len(points), 2),
        }
    latest = inc.briefings[-1] if inc.briefings else None
    return {
        "incident_id": inc.incident_id,
        "severity": inc.severity,
        "coords": coords,
        "detection_count": len(inc.detection_ids),
        "persons_estimated": latest.persons_estimated if latest else None,
    }


async def _gather_grounding(mesh: AgentMesh, req: TaskTranslateRequest) -> str:
    """Build the user-content JSON: operator request + incidents + fleets."""
    incidents = [
        inc
        for inc in await _list_live_models(mesh, INCIDENT_PREFIX, IncidentState)
        if not inc.resolved
    ]

    det_coords: dict[str, Coords] = {}
    if incidents:
        detections = await _list_live_models(mesh, DETECTION_PREFIX, DetectionRecord)
        det_coords = {d.detection_id: d.coords for d in detections}

    payload = {
        "operator_id": req.operator_id,
        "text": req.text,
        "open_incidents": [_incident_summary(inc, det_coords) for inc in incidents],
        "available_fleets": _available_fleets(await mesh.catalog()),
    }
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Translation core (one LLM call, no chains)
# ---------------------------------------------------------------------------


async def translate(mesh: AgentMesh, req: TaskTranslateRequest) -> TaskCommand:
    """Ground, then ONE structured LLM call validated against TaskCommand."""
    user_content = await _gather_grounding(mesh, req)
    try:
        return await structured_llm_call(
            model=LLM_MODEL_TASKER,
            system=SYSTEM_PROMPT,
            user_content=user_content,
            output_model=TaskCommand,
        )
    except LLMUnavailable as e:
        # MeshError passes through the SDK's handler dispatch untouched and
        # reaches the mesh.call() caller as a typed error reply (clean fail,
        # not a timeout). Code is recoverable: the CLI prints and re-prompts.
        raise MeshError(
            message=f"Tasker translation service unavailable: {e}",
            agent=AGENT_NAME,
            code=LLM_UNAVAILABLE_CODE,
        ) from e


# ---------------------------------------------------------------------------
# Registration + process entry point: `python -m demos.wildfire.fleet.tasker`
# ---------------------------------------------------------------------------


def build_agent(mesh: AgentMesh):
    """Register the tasker Responder on ``mesh``. Returns the handler."""

    @mesh.agent(
        AgentSpec(
            name=AGENT_NAME,
            description=AGENT_DESCRIPTION,
            tags=["wildfire", "llm"],
        )
    )
    async def tasker(req: TaskTranslateRequest) -> TaskCommand:
        return await translate(mesh, req)

    return tasker


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    build_agent(mesh)

    async with mesh:
        _log.info("tasker registered (model=%s)", LLM_MODEL_TASKER)
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.Event().wait()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
