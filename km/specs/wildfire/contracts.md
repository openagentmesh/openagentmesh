# Wildfire frozen contracts

**Status:** discussion

Final Pydantic models for the wildfire demo. These supersede the pre-amendment contracts in ADR-0054. They will land verbatim in `demos/wildfire/contracts.py` once implementation begins; this file is the working source of truth until then.

Coordinates are 2D km-scale in a square centered at origin, bounds `[-5, +5]` per axis.

## Common types

```python
from pydantic import BaseModel, Field
from typing import Literal


class Coords(BaseModel):
    """2D simulated coordinates in km from origin."""
    x: float = Field(ge=-5.0, le=5.0)
    y: float = Field(ge=-5.0, le=5.0)


# State enums shared across action fleets.
ActionState = Literal[
    "free",
    "dispatched",
    "en_route",
    "on_site",
    "acting",       # heli: dropping; ffunit: suppressing; medevac: extracting
    "returning",
]


FleetMemberState_StateLit = Literal["free", "busy", "offline"]
```

## Environment + scenario

```python
class ThermalGrid(BaseModel):
    """Snapshot of the simulated thermal field."""
    timestamp: float
    cells: list[tuple[Coords, float]]  # cell center + temperature in degrees C


class FireSpawn(BaseModel):
    """User-driven hotspot creation from the scenario UI."""
    coords: Coords
    magnitude: float                   # initial temperature, degrees C


class FireSuppress(BaseModel):
    """Action-fleet feedback closing the loop into fire-sim."""
    source_instance_id: str
    coords: Coords
    intensity: float                   # 0..1, fraction of local fire reduced this tick


class ChaosKill(BaseModel):
    """Scenario UI -> targeted instance: self-terminate."""
    target_instance_id: str
    reason: str = "demo chaos"
```

## Detection lifecycle (KV-stored)

```python
DetectionState = Literal["pending", "assigned", "surveyed"]


class SurveyResult(BaseModel):
    """Drone-produced intelligence appended to a DetectionRecord."""
    surveyor_instance_id: str
    timestamp: float
    fire_visible: bool
    persons_detected: int
    structures_visible: int
    notes: str = ""


class DetectionRecord(BaseModel):
    """KV value at wildfire.detection.{detection_id}.

    Lifecycle:
      pending  -> assigned:{drone_instance_id}  -> surveyed
    """
    detection_id: str
    state: DetectionState | str        # str shape allows "assigned:{instance_id}" form
    coords: Coords
    severity: float                    # 0..1, derived from temperature
    detector_instance_id: str
    created_at: float
    last_updated: float
    survey: SurveyResult | None = None
    incident_id: str | None = None     # set by briefer once correlated
```

## Fleet presence (KV-stored, shared across all action and survey fleets)

```python
class FleetMemberState(BaseModel):
    """KV value at wildfire.fleet.{zone}.{type}.{instance_id}."""
    instance_id: str
    zone: Literal["high-alt", "low-alt", "ground"]
    fleet_type: Literal["uav", "drone", "heli", "ffunit", "medevac"]
    coords: Coords
    state: FleetMemberState_StateLit
    current_assignment: str | None = None   # detection_id or order_id when busy
    last_updated: float
```

## Action fleet dispatch (queue-grouped request/reply)

```python
class DispatchOrder(BaseModel):
    """Operator -> action fleet: do this thing here."""
    order_id: str
    target_coords: Coords
    incident_id: str | None = None
    priority: Literal["low", "med", "high"]
    operator_id: str
    issued_at: float
    persons_estimated: int = 0          # used by medevac; 0 for heli/ffunit


class DispatchAck(BaseModel):
    """Action fleet -> operator: yes/no with ETA."""
    accepted: bool
    instance_id: str | None             # the unit that accepted
    eta_seconds: float | None
    reason: str | None = None           # populated when accepted=False
```

## Action fleet status feeds (pubsub)

Each action fleet emits a typed status payload on its instance-suffixed status subject (`mesh.action.heli.{id}.status`, etc.). Different fleet types may have slightly different state vocabularies; the per-status models keep this explicit.

```python
class HeliStatus(BaseModel):
    instance_id: str
    order_id: str | None
    state: ActionState
    coords: Coords
    water_remaining_pct: float = Field(ge=0.0, le=1.0)
    timestamp: float


class FFUnitStatus(BaseModel):
    instance_id: str
    order_id: str | None
    state: ActionState
    coords: Coords
    reserves_remaining_pct: float = Field(ge=0.0, le=1.0)
    persons_at_risk_observed: int = 0   # surface for operator to dispatch medevac
    timestamp: float


class MedevacStatus(BaseModel):
    instance_id: str
    order_id: str | None
    state: ActionState
    coords: Coords
    capacity_used: int                   # current persons aboard
    capacity_max: int = 4
    timestamp: float
```

## Briefing + incident (KV + pubsub)

```python
RecommendedAction = Literal[
    "dispatch_heli",
    "dispatch_ffunit",
    "dispatch_medevac",
    "evacuate",
    "monitor",
]


class IncidentBriefing(BaseModel):
    """Pubsub at mesh.briefing.{incident_id}, generated by briefer LLM."""
    incident_id: str
    severity: Literal["low", "med", "high", "critical"]
    summary: str = Field(max_length=280)        # LLM-generated, audit-friendly
    persons_estimated: int
    structures_at_risk: int
    recommended_actions: list[RecommendedAction]
    sources: list[str]                          # detection IDs the briefing covers
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    issued_at: float
    issuing_instance_id: str


class IncidentState(BaseModel):
    """KV value at wildfire.incident.{incident_id}, briefer-owned."""
    incident_id: str
    detection_ids: list[str]                    # all detections clustered into this incident
    last_briefing_at: float                     # CAS lease for tick gating
    briefings: list[IncidentBriefing]           # full history for narrator + dashboard
    severity: Literal["low", "med", "high", "critical"]
    resolved: bool = False
    resolved_at: float | None = None
```

## Tasker (LLM translation)

```python
class TaskTranslateRequest(BaseModel):
    operator_id: str
    text: str                                   # natural language from operator


class TaskCommand(BaseModel):
    target_fleet: Literal["heli", "ffunit", "medevac"]
    coords: Coords
    incident_id: str | None
    priority: Literal["low", "med", "high"]
    persons_estimated: int = 0
    rationale: str                              # LLM explanation, audit
```

## Operator audit

```python
class FirefighterIntent(BaseModel):
    """Pubsub at mesh.fire.{operator_id}.intent — raw NL audit."""
    operator_id: str
    text: str
    issued_at: float
```

## Stats + narrative

```python
class SwarmStats(BaseModel):
    """Pubsub at mesh.swarm.stats every 10s."""
    timestamp: float
    uavs_active: int
    uavs_total: int
    drones_active: int
    drones_total: int
    helis_active: int
    helis_total: int
    ffunits_active: int
    ffunits_total: int
    medevacs_active: int
    medevacs_total: int
    incidents_open: int
    incidents_resolved: int
    fires_detected_total: int
    persons_recovered_total: int


class Narrative(BaseModel):
    """Pubsub at mesh.swarm.narrative every 5 minutes."""
    period_start: float
    period_end: float
    text: str = Field(max_length=1000)
    incident_ids_referenced: list[str]
```

## Open questions on contracts

- `DetectionRecord.state`: `Literal[...] | str` is a compromise to support `"assigned:{instance_id}"`. Cleaner: a discriminated union (`PendingState`, `AssignedState`, `SurveyedState`). Defer until implementation discomfort forces the issue.
- `ActionState` is shared across heli/ffunit/medevac with the understanding that `acting` means different physical actions. Leave as-is for v1; split if narrative or rendering needs to distinguish.
- Should `IncidentState` carry the resolved fire-sim feedback (e.g., "this incident is closed because temperature returned to ambient")? Out of v1; briefer's resolution heuristic is documented as best-effort.

## Ownership

The frozen contracts are the demo's wire format. Once `demos/wildfire/contracts.py` exists, this file becomes a documentation aid; the Python module is canonical. ADR-0054 amendment notes this transition.
