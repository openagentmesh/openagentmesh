# ADR-0054: Wildfire incident response demo (multi-fleet portfolio project)

- **Type:** demo / portfolio
- **Date:** 2026-05-04
- **Status:** spec
- **Depends on:** Phase 1 SDK (AgentMesh, `@mesh.agent`, pub/sub, request/reply, queue groups, KV). For the public-mesh variant: ADR-0038 (NATS auth).
- **Related:** ADR-0019 (OAM vs MCP differentiation by topology), ADR-0007 (plain Pydantic for structured I/O), ADR-0042 (Watcher pattern), ADR-0048 (mesh-native observability).
- **Source:** conversation 2026-05-04 (portfolio demo design; converged on multi-fleet wildfire response after rejecting newsroom and document-pipeline alternatives).
- **Detailed specs:** [`km/specs/wildfire/`](../specs/wildfire/index.md) holds per-agent specs, the dashboard spec, and an `sdk-desiderata.md` collecting API gaps that surfaced while shaping the demo. This ADR remains the umbrella decision (scenario lock, frozen contracts, frozen subject map, scope fences); the specs folder is where each agent's behaviour is iteratively shaped and where SDK requirements that bubble up are tracked toward their own ADRs.

## Context

OAM's portfolio demo must show something Discord-as-bus and single-process orchestrators (LangGraph, CrewAI, OpenClaw) cannot replicate. The conversation that led to this ADR converged on three filters a candidate demo must pass:

1. **Throughput Discord cannot carry** (Discord rate-limits at ~5 msg/s per channel, ~50/s per bot).
2. **Structured machine-speed payloads** that are awkward to encode as chat strings.
3. **Topology that breaks single-process orchestrators** (independent processes, real fault tolerance, dynamic peer discovery).

A multi-fleet wildfire incident response simulation hits all three. It is also visually compelling, politically clean (civil emergency, not military), runs on a developer laptop, and has a low-cost public hosted variant for visitor participation.

The demo doubles as a dogfooding exercise for Phase 1 primitives: pub/sub fan-out, queue groups for fault-tolerant dispatch, request/reply for typed tasking, catalog-driven discovery, and `AgentMesh.local()` for laptop runs.

## Decision

Build a wildfire incident response simulation as the canonical OAM portfolio demo. Five fleet types, two LLM peer agents, and two infrastructure agents communicate exclusively via mesh subjects. No central orchestrator. The same scenario runs locally (recorded video, laptop) and as a public open mesh (visitor participation) once auth lands.

### Architectural invariant

LLM agents are **peers on the mesh, not coordinators above it**. Reactive cascades happen through direct pub/sub subscriptions between fleet agents. LLMs subscribe to the same bus and produce briefings or translate natural-language input into structured commands. A briefing is a published event; a translated task is a typed `mesh.call()` payload. The mesh's existing routing handles delivery. Violating this invariant would rebuild CrewAI inside the demo and undermine OAM's positioning.

### Fleet inventory

> **Amended 2026-05-08** during shaping in `km/specs/wildfire/`. Original inventory had per-fleet flat names and overstated default scale; amendment introduces zone-channel naming (`high-alt`, `low-alt`, `ground`), drop the per-instance UAV multiplicity, add water-bombing helicopter as a low-alt action fleet, and split the original "firefighter unit" into the in-world `ground.ffunit` action fleet plus a separate operator CLI process. Action fleets (heli, ffunit, medevac) are queue-grouped on dispatch. Drones are intelligence-only (survey).

| Fleet | Channel-prefixed name | Process model | Default count | Role |
|---|---|---|---|---|
| UAV (high-altitude) | `high-alt.uav` | own process | 1 | Wide-area thermal surveillance; writes pending detections to KV |
| Drone (low-altitude) | `low-alt.drone` | own process per instance | 5 | Close-range survey via KV-driven election; writes survey results |
| Heli (water-bombing) | `low-alt.heli` | own process per instance | 1-2 | Water-drop suppression; queue-group dispatch |
| Firefighter unit (ground) | `ground.ffunit` | own process per instance | 3 | On-site fire suppression; queue-group dispatch |
| Medevac (ground) | `ground.medevac` | own process per instance | 3 | People recovery; queue-group dispatch |
| Briefer (LLM) | `briefer` | own process, queue group `briefers` | 2 | Correlates detections + surveys into briefings |
| Tasker (LLM) | `tasker` | own process | 1 | Translates operator NL into typed `TaskCommand` |
| Stats ticker | `stats-ticker` | own process | 1 | Aggregate fleet/incident counters every 10s |
| Narrator (LLM) | `narrator` | own process | 1 | Paragraph summaries every 5 min |
| Fire simulator | `fire-sim` | own process | 1 | Publishes thermal grid; consumes spawn + suppression events |

Plus one **firefighter operator CLI** process (not a registered agent; plain `mesh.call` caller).

Total default scale: ~16 fleet processes + scenario UI + admin UI + embedded NATS = workable on any laptop. Scaling up (e.g., 50 drones for production demos) is a CLI flag on the orchestrator.

### Reactive cascade (amended)

> **Second amendment 2026-05-09** — pure-KV world grid. Steps 1-2 (thermal pubsub + UAV subject_source) are replaced by per-cell KV writes under `wildfire.world.cell.*`. fire-sim and UAV both bind a `kv_source` to that namespace. Scenario UI clicks and action-fleet suppression are peer writers; no `mesh.fire.spawn` / `mesh.fire.suppress` pubsub. See `km/specs/wildfire/fire-sim.md` and `uav.md` for the new data flow.

The cascade combines KV state (durable coordination, world + fleet) with pubsub events (fast-moving notifications):

1. **Fire-sim** maintains an in-process 50×50 thermal grid + spread model. Each tick (1 Hz default), it writes `CellState` records to `wildfire.world.cell.<x_idx>.<y_idx>` for cells whose temperature changed materially. Cells decaying to ambient are deleted (sparse-KV invariant). fire-sim also has a `kv_source` on the same namespace and integrates external writes (clicks, action-fleet suppression) into its grid; it filters out self-writes via `last_modified_by == mesh.instance_id`.
2. **UAV** has a `kv_source` on `wildfire.world.cell.*`. On each cell update whose temperature crosses threshold inside the UAV's sensor footprint, it **creates a KV record** at `wildfire.detection.{id}` with `state=pending` (idempotent via dedup hash). UAV does NOT pubsub-publish detections; durability is the point.
3. **All drones** watch `wildfire.detection.*` via KV-watch source. On a new pending detection:
   - Each free drone reads peer position records from `wildfire.fleet.low-alt.drone.*` and computes "am I the closest free drone?"
   - The closest free drone attempts a CAS transition `pending -> assigned:{drone_instance_id}`. CAS resolves all races deterministically.
   - The owning drone surveys the area, then CAS-transitions `assigned -> surveyed` with a `SurveyResult` payload attached. It also publishes `mesh.survey.{instance_id}` for fast-reaction visibility.
   - If all drones are busy when a detection arrives, the record stays `pending`. Drones drain the backlog as they free up.
4. **Briefer (LLM)** watches `wildfire.detection.*` and subscribes to `mesh.survey.>`. Correlates events into incidents (cluster by coords + time). On a 30s tick (gated by CAS on the incident's `last_briefing_at`), produces an `IncidentBriefing` and publishes to `mesh.briefing.{incident_id}` + persists in `wildfire.incident.{incident_id}` (KV).
5. **Firefighter operator CLI** subscribes to `mesh.briefing.>`. Operator decides what to do, types NL into the CLI.
6. **Tasker (LLM)** receives `mesh.call("tasker", TaskTranslateRequest)`, translates to a typed `TaskCommand` (target: `heli`, `ffunit`, or `medevac`) constrained by available action fleets from `mesh.catalog()`.
7. **Operator CLI** receives the typed command, optionally confirms with the human, and dispatches via `mesh.call("low-alt.heli", ...)` / `"ground.ffunit"` / `"ground.medevac"`. Each action fleet is a queue-grouped Responder; the first available unit acks with ETA.
8. **Action fleet** (heli / ffunit / medevac) drives or flies to coords, performs its action (water-drop, suppression, extraction), publishes status events on `mesh.action.{type}.{instance_id}.status`, updates own KV record. Optionally feeds suppression events back to fire-sim, closing the loop.
9. **Stats ticker** reads KV every 10s and publishes `SwarmStats` to `mesh.swarm.stats`. **Narrator** publishes 5-min `Narrative` summaries to `mesh.swarm.narrative`.
10. **Scenario UI** (`demos/wildfire/dashboard`) renders the world: map, fire spread (from `wildfire.world.cell.*` KV), fleet positions (from `wildfire.fleet.>` KV), incident markers (from `wildfire.detection.*`), briefings, narrative. Provides a map-click write surface that writes `CellState` records directly to KV (small/medium/large temperature; "off" deletes the cell key) and a chaos-kill button (publishes to a chaos subject). **Admin UI** (ADR-0056) renders the mesh control plane: agent registry, contract viewer, invocation sandbox, event feed. The two UIs together are the demo's full visualization.

### Subject + KV map (amended)

Frozen in this ADR after the amendment. New subjects/keys require an ADR amendment.

> **Second amendment 2026-05-09** — pure-KV world grid pivot. Removed `mesh.environment.thermal`, `mesh.fire.spawn`, `mesh.fire.suppress` from the pubsub map. Added `wildfire.world.cell.*` KV namespace carrying `CellState`. World mutations (clicks, action-fleet suppression, fire-sim spread deltas) all write to the same namespace; LOOP-01 (action-fleet feedback into fire-sim) collapses into the same path.

**Pubsub subjects:**

| Subject | Direction | Payload |
|---|---|---|
| `mesh.survey.{drone_instance_id}` | broadcast | `SurveyResult` |
| `mesh.briefing.{incident_id}` | broadcast | `IncidentBriefing` |
| `mesh.action.heli.{instance_id}.status` | broadcast | `HeliStatus` |
| `mesh.action.ffunit.{instance_id}.status` | broadcast | `FFUnitStatus` |
| `mesh.action.medevac.{instance_id}.status` | broadcast | `MedevacStatus` |
| `mesh.fire.{operator_id}.intent` | broadcast | `FirefighterIntent` |
| `mesh.swarm.stats` | broadcast | `SwarmStats` |
| `mesh.swarm.narrative` | broadcast | `Narrative` |
| `mesh.chaos.kill.{instance_id}` | broadcast (from scenario UI) | empty payload, instance self-terminates |

**Auto-mapped invocation subjects** (per ADR-0049, derived from agent name):

| Agent | Invocation subject (auto) | Payload |
|---|---|---|
| `low-alt.heli` (queue group) | `mesh.agent.low-alt.heli` | `DispatchOrder` -> `DispatchAck` |
| `ground.ffunit` (queue group) | `mesh.agent.ground.ffunit` | `DispatchOrder` -> `DispatchAck` |
| `ground.medevac` (queue group) | `mesh.agent.ground.medevac` | `DispatchOrder` -> `DispatchAck` |
| `tasker` | `mesh.agent.tasker` | `TaskTranslateRequest` -> `TaskCommand` |

**KV namespace** (in the `wildfire` JetStream KV bucket — separate from OAM-internal `mesh-context` per ADR-0025):

| Key pattern | Owner | Payload |
|---|---|---|
| `wildfire.world.cell.<x_idx>.<y_idx>` | fire-sim spread tick + dashboard click + action-fleet suppression (peer writers) | `CellState` (coords, temperature, last_modified_at, last_modified_by). Sparse — ambient cells have no key. |
| `wildfire.detection.{id}` | UAV creates; drones CAS-update; briefer reads | `DetectionRecord` (state, coords, severity, ts, detector_id, optional survey_result) |
| `wildfire.fleet.{zone}.{type}.{instance_id}` | each fleet member writes own | `FleetMemberState` (coords, state, last_updated) |
| `wildfire.incident.{id}` | briefer (CAS) | `IncidentState` (events list, briefings history, current severity, recommended_actions, last_briefing_at) |

### Frozen contracts

> **Amendment note.** The contracts below are pre-amendment. Several have evolved during shaping in `km/specs/wildfire/`:
> - `ThermalDetection` becomes a richer `DetectionRecord` with a `state` field (KV-stored); see `uav.md`, `drone.md`.
> - `MedevacDispatch` / `MedevacAck` generalize to `DispatchOrder` / `DispatchAck` shared across heli, ffunit, medevac.
> - `MedevacStatus` joins peers `HeliStatus` and `FFUnitStatus` with the same shape, parametric on action type.
> - `TaskCommand.target_fleet` now `Literal["heli", "ffunit", "medevac"]` (action fleets only).
> - `SwarmStats` gains `helis_active`, `ffunits_active`; renames `medevac_active` -> `medevacs_active`.
> - New contracts: `FleetMemberState`, `IncidentState`, `DetectionRecord`.
> - **Second amendment 2026-05-09:** removed `ThermalGrid`, `FireSpawn`, `FireSuppress` (the pubsub-based world-state contracts). Added `CellState` for the per-cell KV records under `wildfire.world.cell.*` per the pure-KV world grid pivot.
>
> Final contracts will be written into `demos/wildfire/core/contracts.py` during implementation. The list below is preserved for historical reference; the per-agent specs and `km/specs/wildfire/contracts.md` are the working source of truth for v1.

```python
from pydantic import BaseModel, Field
from typing import Literal

# Coordinates are simulated 2D grid coords (km from origin).
class Coords(BaseModel):
    x: float
    y: float

class ThermalGrid(BaseModel):
    timestamp: float
    cells: list[tuple[Coords, float]]  # cell center + temperature

class ThermalDetection(BaseModel):
    detector_id: str
    coords: Coords
    temperature: float
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: float

class SurveyResult(BaseModel):
    drone_id: str
    incident_id: str
    coords: Coords
    fire_visible: bool
    persons_detected: int
    structures_visible: int
    timestamp: float

class IncidentBriefing(BaseModel):
    incident_id: str
    severity: Literal["low", "med", "high", "critical"]
    summary: str  # LLM-generated, max 280 chars (audit-friendly)
    persons_estimated: int
    structures_at_risk: int
    recommended_actions: list[Literal["dispatch_medevac", "dispatch_drone", "evacuate", "monitor"]]
    sources: list[str]  # event IDs the briefing was derived from

class MedevacDispatch(BaseModel):
    incident_id: str
    target_coords: Coords
    persons_estimated: int
    priority: Literal["low", "med", "high"]
    requested_by: str  # firefighter unit id

class MedevacAck(BaseModel):
    accepted: bool
    medevac_id: str | None
    eta_seconds: float | None
    reason: str | None  # if rejected

class MedevacStatus(BaseModel):
    medevac_id: str
    incident_id: str
    state: Literal["en_route", "on_site", "extracting", "returning", "available"]
    coords: Coords

class FirefighterIntent(BaseModel):
    unit_id: str
    text: str  # raw NL, kept for audit
    issued_at: float

class TaskTranslateRequest(BaseModel):
    unit_id: str
    text: str

class TaskCommand(BaseModel):
    target_fleet: Literal["drone", "uav", "medevac"]
    action: Literal["survey", "thermal_recheck", "medevac_dispatch", "monitor"]
    coords: Coords
    priority: Literal["low", "med", "high"]
    rationale: str  # LLM explanation, for audit

class SwarmStats(BaseModel):
    timestamp: float
    drones_active: int
    uavs_active: int
    medevac_active: int
    incidents_open: int
    incidents_resolved: int
    persons_recovered: int
    fires_detected_total: int

class Narrative(BaseModel):
    period_start: float
    period_end: float
    text: str  # max 1000 chars
    incident_ids_referenced: list[str]
```

### LLM peer reliability

Both LLM peers (Briefer, Tasker) emit Pydantic-validated outputs. Pydantic validation is the safety net against hallucinated fleets, malformed coordinates, or invalid action types. If the LLM produces an invalid `TaskCommand` (e.g., `target_fleet="hovercraft"`), validation fails before publication and the request returns a typed error.

The Tasker's prompt is constructed from sanitized structured fields only: `unit_id`, current open incidents (from KV), available fleet capabilities (from `mesh.catalog()`). It never sees raw text from other agents, only firefighter NL input. This bounds prompt-injection surface.

### Code sample (the DX contract)

A skeleton showing the protocol-first feel. Fleets are independent processes; mesh wiring is decorator-only.

```python
# fleets/uav.py
from openagentmesh import AgentMesh, AgentSpec, Subscribe
from demos.wildfire.contracts import ThermalGrid, ThermalDetection, Coords

mesh = AgentMesh()

@mesh.agent(
    AgentSpec(name="uav.high-alt", description="Wide-area thermal sweep UAV"),
    subscribes=[Subscribe("mesh.environment.thermal")],
)
async def uav_thermal_sweep(grid: ThermalGrid) -> None:
    for coords, temp in grid.cells:
        if temp > THRESHOLD and within_sensor_range(coords):
            await mesh.publish(
                "mesh.detection.thermal",
                ThermalDetection(
                    detector_id=UAV_ID,
                    coords=coords,
                    temperature=temp,
                    confidence=confidence_from_temp(temp),
                    timestamp=time.time(),
                ),
            )

if __name__ == "__main__":
    asyncio.run(mesh.run())
```

```python
# fleets/drone.py
@mesh.agent(
    AgentSpec(name="drone.low-alt", description="Close-range survey drone", queue_group="drones"),
    subscribes=[Subscribe("mesh.detection.thermal")],
)
async def drone_survey(detection: ThermalDetection) -> None:
    if not nearest_available(detection.coords):
        return  # let another drone in the queue group take it
    await fly_to(detection.coords)
    result = perform_survey(detection.coords)
    await mesh.publish(f"mesh.survey.{DRONE_ID}", result)
```

```python
# fleets/briefer.py (LLM peer)
@mesh.agent(
    AgentSpec(name="briefer", description="Structured incident briefings from raw events"),
    subscribes=[
        Subscribe("mesh.detection.thermal"),
        Subscribe("mesh.survey.>"),
    ],
)
async def briefer(event: ThermalDetection | SurveyResult) -> None:
    incident_id = correlate_to_incident(event)
    await update_incident_state(incident_id, event)  # KV
    if briefing_threshold_reached(incident_id):
        briefing = await llm_produce_briefing(incident_id)  # returns IncidentBriefing
        await mesh.publish(f"mesh.briefing.{incident_id}", briefing)
```

```python
# fleets/tasker.py (LLM peer, request/reply)
@mesh.agent(
    AgentSpec(name="tasker", description="Translate firefighter NL into typed TaskCommand"),
)
async def tasker(req: TaskTranslateRequest) -> TaskCommand:
    catalog = await mesh.catalog()  # discover available fleets
    return await llm_translate(req, catalog)  # Pydantic-validated TaskCommand
```

```python
# fleets/firefighter.py (human-in-the-loop)
async def cli_loop():
    while True:
        text = input("> ")
        cmd = await mesh.call("tasker", TaskTranslateRequest(unit_id=UNIT, text=text))
        if cmd.target_fleet == "medevac" and cmd.action == "medevac_dispatch":
            ack = await mesh.call(
                "medevac.dispatch",
                MedevacDispatch(
                    incident_id=current_incident,
                    target_coords=cmd.coords,
                    persons_estimated=current_persons,
                    priority=cmd.priority,
                    requested_by=UNIT,
                ),
            )
            print(f"medevac {ack.medevac_id} ETA {ack.eta_seconds}s")
```

### Visualization

Two web UIs run side by side (per `km/specs/wildfire/admin-ui-integration.md`):

- **Scenario UI** (`demos/wildfire/dashboard/`) renders the world: map with fire spread (from `wildfire.world.cell.*` KV), fleet positions + trails (from `wildfire.fleet.>` KV), incident markers (from `wildfire.detection.*`), briefing + narrative feeds. Map-click writes `CellState` records to KV (small/medium/large temperature; "off" deletes the key). Stack: **Svelte 5 + Vite + plain HTMLCanvas + FastAPI + WebSocket** (per amended `dashboard.md`).
- **Admin UI** (ADR-0056, amended) renders the mesh control plane: agent registry, contract viewer, invocation sandbox, event feed. Stack: **React + Vite + Tailwind + nats.ws + tiny static-asset server** — the browser is a first-class mesh client.

Two narratives, two stacks, both supported by OAM. The recording shows them side by side.

### Hosting and cost

**Local laptop (canonical):** all fleets run via `uv run` in separate terminals. NATS embedded via `AgentMesh.local()` from a `bootstrap.py` orchestrator (which only starts the mesh; fleets connect to it). Cost: $0.

**Public hosted variant:** small VPS ($5-10/mo). One process per fleet type runs as baseline. NATS server with auth (ADR-0038 required). Visitors clone a starter repo and run their own fleet processes pointing at the public NATS URL. LLM bill: ~$10-30/mo (briefer + narrator + tasker, with caching).

Total recurring cost for the public variant: under $50/mo. Sustainable indefinitely on demo budget.

### Scope fences

**In scope (v1):**

- Five fleet types listed above, with the frozen contracts.
- One canonical scenario (Sector 7 thermal anomaly → drones survey → briefing → firefighter dispatches medevac → resolution) as the recorded demo.
- Local laptop run via `uv run demos/wildfire/...`.
- Web dashboard with the components listed.
- Recorded 90-second video for the README.
- Cookbook recipe in `docs/cookbook/wildfire-incident.md`.

**Out of scope (v1):**

- Real autonomy (e.g., firefighter unit acts on briefings without human input). Add a deterministic policy agent post-v1 if useful.
- Cross-incident memory or learning.
- Polyglot fleets (TS, Go) — Phase 4 follow-up.
- Public open mesh — gated on ADR-0038.
- Adversarial / abuse handling (visitor spoofing, rate limit attacks).
- Real geographic data, real GIS, real weather.
- Kubernetes / Docker compose deployment story.
- Multiple concurrent incidents in one scenario (start with one, expand if cheap).

**Anti-scope (will not be built):**

- Defense / military framing. Civil emergency only.
- Any real-world drone control. Sim only.
- LLM agent that "decides" who does what beyond the typed Tasker translation. The LLM is a peer, never the conductor.

### Branding

The demo lives at `demos/wildfire/` (git path) and is referenced in docs as "Wildfire Incident Response demo" or "the wildfire demo." Avoid "swarm" in user-facing copy: heterogeneous fleets, not a uniform swarm.

### Sequencing

1. Skeleton phase (laptop only): UAV + drone fleet only, no LLM, console viz. Validates throughput and queue groups carry the load.
2. Add medevac fleet, firefighter CLI, briefer LLM. Records a working scenario.
3. Add tasker LLM + dashboard + narrator + stats ticker.
4. Record canonical 90-second video. Ship as portfolio piece.
5. (Post-ADR-0038) Public hosted variant + visitor starter repo.
6. (Phase 4) Polyglot follow-up: TS or Go fleet joining the same mesh.

## Consequences

- New top-level directory `demos/wildfire/` with five fleet packages, contracts module, and dashboard. Independent of the SDK package; depends only on the public `openagentmesh` API.
- The frozen contracts module (`demos/wildfire/contracts.py`) becomes a reference for "how to design contracts for a heterogeneous-fleet system." Worth highlighting in the cookbook.
- Two LLM dependencies enter the demo (Briefer, Tasker, Narrator). The `claude-api` skill applies. LLM provider is configurable; default is Claude Haiku for narrator + ticker-cadence agents, Sonnet for briefer (richer reasoning). Tasker uses Sonnet with strict structured output.
- The dashboard is a NATS subscriber-only client written against the public `openagentmesh` API. It validates that read-only mesh consumers are first-class.
- Demo dogfoods: Phase 1 SDK, ADR-0007 (Pydantic), ADR-0009 (catalog discovery), ADR-0014 (single-key catalog), ADR-0028 (typed CatalogEntry), ADR-0031 (capabilities), ADR-0034 (subscribe + publisher), ADR-0042 (watcher pattern, briefer), ADR-0049 (dotted agent names).
- Surfaces SDK gaps. Likely candidates to discover during build: lifecycle ergonomics for fleet processes (currently each process needs its own boilerplate), cleaner publisher API, KV interaction for incident state. These should be tracked as ADRs as they emerge, not pre-empted.
- Recording the canonical video doubles as the README marketing artifact and the conference-talk demo material.

## Alternatives Considered

**Single uniform drone swarm (200 drones, no fleet types).** Stronger throughput argument (visceral numbers) and simpler build. Weaker topology argument (it's many copies of one agent type). Rejected as the primary demo because the heterogeneous cascade is the harder-to-fake story. The simple swarm survives as a possible "supporting" demo if the multi-fleet build runs long.

**Newsroom / agent social network.** Discord-as-bus replicates the observable behavior. Rejected per conversation 2026-05-04.

**Document processing pipeline.** Defensible against Discord (high throughput + structured payloads + polyglot stages) but visually boring. Rejected as the headline portfolio demo. Reserve as a possible enterprise-targeted supporting demo.

**Market simulation (5000 traders).** Strong on throughput, weaker on topology and visual narrative. Niche audience (finance / quant). Rejected as primary; viable as a supporting demo for technical conferences.

**Pandemic / epidemiology simulation.** Topical-fatigued, depressing framing. Same architectural shape as wildfire but worse storytelling. Rejected.

**Defense / military drone swarm framing.** Architecturally identical to wildfire but politically loaded. Rejected explicitly to keep the demo broadly shareable.

**Make the LLM the orchestrator (firefighter chats and the LLM directly dispatches).** Rejected. This rebuilds CrewAI inside the demo and weakens OAM's positioning. The LLM as a peer that translates NL into a typed `TaskCommand` (which the UI then publishes via mesh) preserves the no-orchestrator invariant while still giving the human a chat-shaped UX.

**Defer scenario lock and let the demo evolve organically.** Rejected. The conversation explicitly identified scope-creep risk (the scenario expanded from "swarm covers a fire" to "incident management system" within minutes). Locking the scenario, fleet list, and contracts in this ADR is the discipline that makes the demo shippable.
