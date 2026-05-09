"""Frozen Pydantic models for the wildfire demo (Phase 1 subset).

Source of truth: ``km/specs/wildfire/contracts.md`` (amended 2026-05-09 — pure-KV
world grid pivot). The amendment dropped the three pubsub-era world-state
contracts (see the spec file for their names) and added ``CellState`` for the
per-cell KV records under ``wildfire.world.cell.<x_idx>.<y_idx>``.

This module ships the Phase 1 inventory only (per Amendment A-07 in
``.planning/phases/01-detection-foundation/01-CONTEXT.md``):

- ``Coords`` (shared coordinate model, [-5, +5] km bounds per axis)
- ``CellState`` (sparse world-grid KV value)
- ``DetectionRecord`` + ``SurveyResult`` (detection lifecycle)
- ``FleetMemberState`` (1 Hz heartbeat KV value)
- ``DispatchOrder`` + ``DispatchAck`` (action fleet request/reply)
- ``HeliStatus`` + ``FFUnitStatus`` (action fleet status feeds)
- Shared ``Literal`` aliases: ``ActionState``, ``FleetMemberState_StateLit``,
  ``DetectionState``

Out of Phase 1 scope (and therefore out of this module): briefer / tasker
contracts (``IncidentBriefing``, ``IncidentState``, ``TaskCommand``,
``TaskTranslateRequest``), narrator (``Narrative``), stats ticker
(``SwarmStats``), medevac (``MedevacStatus``), chaos (``ChaosKill``), operator
audit (``FirefighterIntent``). They will land alongside the agents that own
them in later phases.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared types + Literal aliases
# ---------------------------------------------------------------------------


class Coords(BaseModel):
    """2D simulated coordinates in km from origin."""

    x: float = Field(ge=-5.0, le=5.0)
    y: float = Field(ge=-5.0, le=5.0)


# State enums shared across action fleets (heli / ffunit / medevac).
ActionState = Literal[
    "free",
    "dispatched",
    "en_route",
    "on_site",
    "acting",  # heli: dropping; ffunit: suppressing; medevac: extracting
    "returning",
]


# Fleet-member liveness state (heartbeat record).
FleetMemberState_StateLit = Literal["free", "busy", "offline"]


# Detection lifecycle phases. Note: ``DetectionRecord.state`` widens this to
# ``DetectionState | str`` so the ``"assigned:{drone_instance_id}"`` form is
# accepted on the wire.
DetectionState = Literal["pending", "assigned", "surveyed"]


# ---------------------------------------------------------------------------
# World state (KV-stored, per-cell)
# ---------------------------------------------------------------------------


class CellState(BaseModel):
    """KV value at ``wildfire.world.cell.<x_idx>.<y_idx>``.

    Sparse: ambient cells have no key. Cells decaying back to ambient are
    deleted. All writers populate ``last_modified_by`` so fire-sim's
    ``kv_source`` self-write filter can skip its own deltas.
    """

    coords: Coords  # cell center, snapped to the 200m grid
    temperature: float  # degrees Celsius, expected range [25, 800]
    last_modified_at: float
    last_modified_by: str  # writer's mesh.instance_id


# ---------------------------------------------------------------------------
# Detection lifecycle (KV-stored)
# ---------------------------------------------------------------------------


class SurveyResult(BaseModel):
    """Drone-produced intelligence appended to a ``DetectionRecord``."""

    surveyor_instance_id: str
    timestamp: float
    fire_visible: bool
    persons_detected: int
    structures_visible: int
    notes: str = ""


class DetectionRecord(BaseModel):
    """KV value at ``wildfire.detection.{detection_id}``.

    Lifecycle: ``pending -> assigned:{drone_instance_id} -> surveyed``.
    """

    detection_id: str
    state: DetectionState | str  # str shape allows "assigned:{instance_id}" form
    coords: Coords
    severity: float  # 0..1, derived from temperature
    detector_instance_id: str
    created_at: float
    last_updated: float
    survey: SurveyResult | None = None
    incident_id: str | None = None  # set by briefer once correlated


# ---------------------------------------------------------------------------
# Fleet presence (KV-stored, shared across all action and survey fleets)
# ---------------------------------------------------------------------------


class FleetMemberState(BaseModel):
    """KV value at ``wildfire.fleet.{zone}.{type}.{instance_id}``."""

    instance_id: str
    zone: Literal["high-alt", "low-alt", "ground"]
    fleet_type: Literal["uav", "drone", "heli", "ffunit", "medevac"]
    coords: Coords
    state: FleetMemberState_StateLit
    current_assignment: str | None = None  # detection_id or order_id when busy
    last_updated: float


# ---------------------------------------------------------------------------
# Action fleet dispatch (queue-grouped request/reply)
# ---------------------------------------------------------------------------


class DispatchOrder(BaseModel):
    """Operator -> action fleet: do this thing here."""

    order_id: str
    target_coords: Coords
    incident_id: str | None = None
    priority: Literal["low", "med", "high"]
    operator_id: str
    issued_at: float
    persons_estimated: int = 0  # used by medevac; 0 for heli/ffunit


class DispatchAck(BaseModel):
    """Action fleet -> operator: yes/no with ETA."""

    accepted: bool
    instance_id: str | None  # the unit that accepted
    eta_seconds: float | None
    reason: str | None = None  # populated when accepted=False


# ---------------------------------------------------------------------------
# Action fleet status feeds (pubsub)
# ---------------------------------------------------------------------------


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
    persons_at_risk_observed: int = 0  # surface for operator to dispatch medevac
    timestamp: float
