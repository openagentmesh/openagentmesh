# Drone (low-altitude)

**Status:** discussion
**Identity:** `low-alt.drone` (default 5 instances)

## Purpose

Close-range survey. Watches the KV detection queue, elects the closest free drone for each pending detection via CAS, surveys the area, and writes the survey result. Drones are intelligence providers: they do not suppress fires or extract people.

## Triggers

- KV-watch source: `wildfire.detection.*`. New `pending` records trigger the election logic.
- KV-watch source: `wildfire.fleet.low-alt.drone.*`. Peer position changes are observed (used to recompute fitness when peers transition free/busy).

## Outputs

- KV write: detection record CAS-transitions `pending -> assigned:{drone_instance_id} -> surveyed`. Survey payload attached on the `surveyed` write.
- KV write: own fleet state at `wildfire.fleet.low-alt.drone.{instance_id}` (heartbeat + state changes).
- Pubsub: `mesh.survey.{instance_id}` (broadcast event with the `SurveyResult` payload). Used by the briefer for fast reactions and by the admin UI for the live event feed. KV write remains the source of truth.

## State

- Internal: position, busy/free flag, current assignment.
- KV (own): `wildfire.fleet.low-alt.drone.{instance_id}` carrying `coords`, `state`, `current_detection_id`, `last_updated`.

## Lifecycle

- Always-on. 5 instances default. Independent processes. Killing one is a chaos demo.

## Election protocol

When a `pending` detection is observed (either via KV-watch OR upon transitioning free):

1. **Read peers.** `mesh.kv.list("wildfire.fleet.low-alt.drone")` returns all peer position records (#9).
2. **Filter free peers.** Drop self and any peer whose `state != "free"`.
3. **Compute fitness.** Distance from each free drone (including self) to the detection coords.
4. **Bail if not closest.** If any free peer is closer than self, do nothing this round. The closer peer will attempt the CAS.
5. **Attempt claim.** `try_cas` on the detection record:
   - Re-read inside the CAS context. If `state != "pending"`, exit without writing.
   - Otherwise, set `state = "assigned:{my_instance_id}"`. CAS-write.
   - On success: own the detection.
   - On failure (someone else CAS'd in the meantime): exit silently.
6. **Survey.** Set self `state = "busy"`. Fly to coords (simulated `await asyncio.sleep(distance/speed + survey_time)`). Compute `SurveyResult` (persons detected, structures visible, etc.).
7. **Complete.** CAS the detection: `state = "surveyed"`, attach `survey_result` payload. Publish pubsub event on `mesh.survey.{instance_id}` for visibility. Set self back to `free`.
8. **Drain backlog.** On `free` transition, scan `wildfire.detection.*` for `state == pending` records and run the election on the closest one.

## Reliability

- CAS resolves all races deterministically: exactly one drone wins per pending detection.
- A killed drone mid-survey leaves its assignment hanging. Mitigation: timeout watchdog (briefer or separate cleaner agent observes `assigned:` state with old `last_updated` and reverts to `pending`). v1 may skip this; chaos demo prefers showing the consequence.
- Missed peer position updates: handled implicitly by re-running the election on every relevant KV change.

## Behaviour notes

- Speed: configurable km/sec; default such that a typical survey completes in 5-15s.
- Survey duration: 3-10s simulated work after arrival.
- `SurveyResult` carries: drone instance ID, detection ID, coords, fire visible, persons detected, structures visible, ts.
- Drones do not actively pursue distant detections; if a drone is too far for any plausible response time, the position record's `state=free` with bounded sensor range can disqualify it. v1: no such disqualification, the closest drone always wins regardless of distance.

## Open questions

- Stale-assignment cleanup: who owns the watchdog? Briefer or a dedicated `wildfire.cleaner` agent? Defer; v1 lives without it, document as known limitation.
- Position update rate: 1Hz heartbeat OR event-driven (state change only)? Both. Heartbeat carries `last_updated`; freshness drives liveness.
- Should the drone publish a "considering" intent (so multiple drones don't all start the survey computation in parallel)? No: CAS is the single source of truth, computation is cheap.
- Pubsub event on survey complete: useful for the demo's narrative (fast-moving cascade visible in admin UI), but introduces dual-write semantics. Lean toward keeping it; document KV as authoritative.

## Subject + KV contracts

- KV-watch (source): `wildfire.detection.*`, `wildfire.fleet.low-alt.drone.*`.
- KV write (state): `wildfire.detection.{id}` (CAS), `wildfire.fleet.low-alt.drone.{instance_id}` (heartbeat).
- Pubsub (event): `mesh.survey.{instance_id}` carries `SurveyResult`.

## SDK shape needed

- Declarative KV-watch source on the decorator (#1).
- `mesh.kv.list(prefix)` for one-shot peer reads (#9).
- `mesh.kv.try_cas(key)` (or equivalent) so race-loss is data not exception (#9).
- `mesh.instance_id` (#8) for self-ID and KV record key.
- `mesh.publish(subject, model)` (#2) for survey event emission.
