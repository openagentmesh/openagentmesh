# Firefighter operator (CLI)

**Status:** discussion
**Identity:** plain caller process; not a registered agent.

## Purpose

Human-in-the-loop dispatcher. Single operator drives all action-fleet decisions: when to send heli, ffunit, medevac, and where. The operator is a thin CLI that reads briefings, accepts NL commands, calls the Tasker for typed translation, and dispatches via standard `mesh.call` to action fleets.

This is intentionally narrow for v1. Multi-operator, per-instance targeting, and cross-fleet coordination policies are deferred (see `admin-ui-integration.md` and `sdk-desiderata.md`).

## Triggers

- Stdin: human types commands.
- Subscribes (background): `mesh.briefing.>` (briefing feed prints to a side panel).

## Outputs

- Calls: `mesh.call("tasker", ...)` for NL translation, then `mesh.call("low-alt.heli", ...)` / `"ground.ffunit"` / `"ground.medevac"` based on the typed `TaskCommand`.
- Pubsub: `mesh.fire.{operator_id}.intent` carries raw NL text for audit.

## State

- Internal: operator ID (uuid generated at startup), current briefings buffer for display.
- KV: none in v1.

## Lifecycle

- One process per scenario. Killing it stops dispatch but the cascade continues (existing missions complete).

## Reliability

- This is a thin caller. Errors print to stderr; operator retries.
- No retries on failed dispatches; operator decides what to do next.

## Behaviour notes

- CLI loop: plain `input()` for v1; consider `prompt_toolkit` if a TUI grows.
- Translation flow:
  1. Read NL from stdin.
  2. Publish `FirefighterIntent` audit record.
  3. `cmd = await mesh.call("tasker", TaskTranslateRequest(operator_id=ID, text=text))`.
  4. Show resolved `TaskCommand` to operator with y/n confirmation (CLI flag `--auto-accept` for unattended demo recording).
  5. Issue `mesh.call(target_agent, ...)` based on `cmd.target_fleet`. Target maps:
     - `cmd.target_fleet == "heli"` -> `mesh.call("low-alt.heli", DispatchOrder)`
     - `cmd.target_fleet == "ffunit"` -> `mesh.call("ground.ffunit", DispatchOrder)`
     - `cmd.target_fleet == "medevac"` -> `mesh.call("ground.medevac", DispatchOrder)`
  6. Print the dispatch ack: `accepted`, `instance_id`, `eta_seconds`, optional `reason` if rejected.
- Briefing feed runs in a background task printing to a scrolling region. v1: simple stdout interleave with input prompt.

## Open questions

- TUI vs plain CLI: plain CLI is enough for v1; revisit if scenario UI/CLI ergonomics need attention.
- Auto-accept policy: confidence threshold from Tasker output, or operator flag? v1: flag only.
- Should the operator's intent record cause the fleet to also see the original NL (for audit context)? No: fleets see typed `TaskCommand` only. Audit record is for the dashboard / forensics.

## Subject + KV contracts

- Inbound subscription: `mesh.briefing.>` (consumes `IncidentBriefing`).
- Outbound pubsub: `mesh.fire.{operator_id}.intent` carries `FirefighterIntent`.
- Calls: `tasker`, `low-alt.heli`, `ground.ffunit`, `ground.medevac`.

## SDK shape needed

- Plain caller, no decorator usage. **Works on current SDK** modulo `mesh.publish(subject, model)` (#2) for the audit pubsub.
