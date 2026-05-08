# Firefighter unit

**Status:** discussion

## Purpose

Human-in-the-loop tasking. A firefighter operator types natural language commands; the unit translates them via the Tasker LLM, then issues mesh calls (medevac dispatch, drone surveys) based on the resulting typed `TaskCommand`. The unit also subscribes to briefings to keep situational awareness.

## Triggers

- **CLI input:** stdin loop, no mesh trigger.
- **Subscribes:** `mesh.briefing.{incident_id}` (subscribe with wildcard `mesh.briefing.>` to follow all incidents in v1).

## Outputs

- **Calls:** `mesh.call("tasker", TaskTranslateRequest(...))` then `mesh.call("medevac.dispatch", ...)` etc. depending on `TaskCommand.target_fleet`.
- **Publishes:** `FirefighterIntent` to `mesh.fire.{unit_id}.intent` (raw NL, audit log).

## State

- Internal: unit ID, current incident under attention, briefing log buffer for the operator.
- KV: none in v1.

## Lifecycle

- Always-on while the human operator is at the terminal. Multiple firefighter units can run in parallel.

## Reliability

- This is the human-facing surface. If `mesh.call("tasker")` fails, the CLI prints the error and asks again. No retry loops.

## Behaviour notes

- The CLI is a simple `prompt_toolkit` or plain `input()` loop. Stretch goal: TUI with a pane for live briefings.
- Translation flow:
  1. Read NL from stdin.
  2. Publish `FirefighterIntent` (audit).
  3. `cmd = await mesh.call("tasker", TaskTranslateRequest(unit_id=UNIT, text=text))`.
  4. Show the resolved `TaskCommand` to the operator with a y/n confirmation (or auto-accept above a confidence threshold).
  5. Issue `mesh.call(target, ...)` based on `cmd.target_fleet`.
  6. Print the result (medevac ack ETA, etc.).

- Briefing sub runs in a background task that prints to a side pane / scrolling log.

## Open questions

- Does the firefighter need its own typed agent surface (so other components can `mesh.call("firefighter.unit-3", ...)`)? Probably no for v1 - the unit is a sink, not a service.
- Should the operator confirmation be skippable for unattended demo recordings? Yes; CLI flag `--auto-accept` for video capture.
- How does the firefighter pick a target (which medevac dispatch, which drone) when the LLM returns a generic `target_fleet`? It calls the fleet's logical name (`medevac.dispatch`) and lets the queue group pick a unit. The firefighter does not address individual fleet members.

## Subject contracts

Inbound subscription: `IncidentBriefing` on `mesh.briefing.>`. Outbound: `FirefighterIntent`. Calls: `tasker`, `medevac.dispatch`, etc.

## SDK shape needed

- For the briefing subscription, today's `mesh.subscribe(subject="mesh.briefing.>")` works. The CLI is a plain caller, not a registered agent, so it does not need decorator changes.
- For the `FirefighterIntent` publish, public `mesh.publish(subject, model)` (#2).
