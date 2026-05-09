---
phase: 02-cascade-closure
plan: 04
subsystem: wildfire/world
tags: [operator, cli, mesh-call, typed-form, dispatch, plain-caller]
requires:
  - "02-cascade-closure/02-01"   # MedevacStatus contract + Phase 2 constants
  - "01-detection-foundation/01-01"  # Coords + DispatchOrder + DispatchAck (Phase 1)
provides:
  - "demos.wildfire.world.firefighter -- plain-caller operator CLI"
  - "Typed-form dispatch grammar parser (parse_dispatch_line)"
  - "Fleet -> channel mapping (target_agent_for_fleet)"
  - "DispatchAck pretty-printer (format_ack)"
  - "GRAMMAR constant -- usage reminder for the operator"
  - "REPL loop driving mesh.call against low-alt.heli / ground.ffunit / ground.medevac"
affects:
  - "Phase 2 demo run flow: viewer launches the CLI in a separate terminal (D-33) once the orchestrator is up to drive heli/ffunit/medevac dispatch"
  - "Phase 3 lands the --nl flag on top of this same module; the typed path stays as --typed"
tech_stack_added: []   # stdlib + existing SDK + existing wildfire contracts
patterns:
  - "Plain caller pattern: AgentMesh() as async context manager, mesh.call, exit. Mirrors demos/wildfire/world/spawn.py from Phase 1."
  - "Pure helpers (parse_dispatch_line, target_agent_for_fleet, format_ack) split from I/O-bearing repl(); helpers are unit-tested without NATS."
  - "REPL reads stdin via asyncio.to_thread(in_stream.readline) so the loop yields between lines and StringIO can drive it deterministically in tests."
  - "Live tests register stub @mesh.agent responders on AgentMesh.local() under the real fleet names so end-to-end dispatch is exercised without spawning the real heli/ffunit/medevac processes."
key_files_created:
  - "demos/wildfire/world/firefighter.py"
  - "tests/wildfire/unit/test_firefighter_cli.py"
key_files_modified: []
decisions:
  - "Persons field is parsed for every fleet, not enforced to medevac-only. The spec says persons defaults to 0 for non-medevac; the parser does not reject persons on heli/ffunit because the handlers ignore the field. Documented in the parser docstring and the test_parse_persons_only_medevac_meaningful unit test."
  - "Helper signature returns a DispatchOrder with placeholder order_id/operator_id/issued_at; the REPL stamps those at dispatch time via model_copy(update=...). Keeps parse_dispatch_line side-effect-free and unit-testable without uuid/time mocking."
  - "Bad-line policy: print 'error: <reason>' AND the GRAMMAR to stderr (D-31 loud failure), continue the loop. Reuses the same handler for ValueError from parsing and ValueError from target_agent_for_fleet."
  - "MeshError on mesh.call is caught and logged to stderr without exiting; the operator decides what to do next (matches the firefighter.md 'no retries on failed dispatches' note)."
metrics:
  duration_seconds: 218
  tasks_completed: 2
  files_modified: 2
  tests_added: 40
  commits: 3
completed_date: "2026-05-09"
---

# Phase 02 Plan 04: Operator firefighter CLI Summary

Shipped the missing operator-side surface for Phase 2: a plain stdin caller
that parses typed dispatch lines and invokes heli / ffunit / medevac via
`mesh.call`. Two files, three commits, 40 tests. No briefing pane, no
NL-translator hop, no `@mesh.agent` registration -- exactly the "plain
caller process" `firefighter.md` describes.

## What landed

### `demos/wildfire/world/firefighter.py`

A single-file module with three concerns kept distinct:

1. **Pure helpers** (no I/O, no SDK):
   - `parse_dispatch_line(line)` -- typed-form parser. Returns
     `DispatchOrder | None` with placeholder caller-injected fields.
     Empty / `help` / `?` -> `None`. Bad input -> `ValueError`.
   - `target_agent_for_fleet(fleet)` -- routes `heli` to `low-alt.heli`,
     `ffunit` to `ground.ffunit`, `medevac` to `ground.medevac`.
   - `format_ack(ack)` -- one-liner for the `DispatchAck` dict.
   - `GRAMMAR` constant -- usage reminder shown on bad input + on the
     `help` / `?` commands.
2. **REPL loop** `async def repl(mesh, *, operator_id, in_stream,
   out_stream, err_stream, call_timeout)`. Reads one line via
   `asyncio.to_thread(readline)`, classifies, dispatches. EOF breaks.
   `ValueError` on bad input prints `error: ...` + `GRAMMAR` to stderr
   and continues. `MeshError` from the call goes to stderr; the loop
   keeps running.
3. **CLI entry point** `main(argv)`: argparse for `--operator-id`
   (default derived from `mesh.instance_id`), reads `NATS_URL` env
   (default `nats://127.0.0.1:4222` mirroring `spawn.py`),
   `asyncio.run(_run(url, operator_id))`. KeyboardInterrupt -> 0;
   any other exception -> 1 with the message printed to stderr.

### `tests/wildfire/unit/test_firefighter_cli.py`

40 unit tests in three groups:

- **Parser + helpers (24 tests):** valid lines (parametrized over heli /
  ffunit / medevac, with and without persons, case-insensitive),
  empty/help/? returning None, every failure mode (unknown fleet, bad
  priority, out-of-bounds coords, wrong field count, non-float coords,
  non-int persons), persons defaulting and persons-passthrough
  behaviour, `target_agent_for_fleet` mapping (3 entries +
  unknown-raises), `format_ack` accepted + rejected, GRAMMAR constant
  mentions every fleet and every priority.
- **Source-text negative gates (12 tests):** the file does NOT contain
  `@mesh.agent(`, `AgentSpec(`, `subject_source(`, `kv_source(`,
  `mesh.briefing`, `tasker` (case-insensitive), `bucket=`/`prefix=`/
  `model=` (A-09), or any of the dropped pubsub-era artefacts
  (`ThermalGrid`, `FireSpawn`, `FireSuppress`,
  `mesh.environment.thermal`, `mesh.fire.spawn`, `mesh.fire.suppress`).
- **Live REPL (5 tests):** drive `repl()` against `AgentMesh.local()`
  with stub responders registered under the real fleet names
  (`low-alt.heli`, `ground.ffunit`, `ground.medevac`). Assert dispatch
  succeeds for each fleet, bad lines do not exit the REPL, `help` prints
  the grammar without breaking the next dispatch, empty input exits
  cleanly without a stdout dispatch line.

## Grammar accepted

Per D-31, the typed grammar is:

```
<fleet> <x> <y> <priority> [persons]
```

- `fleet`    `heli` | `ffunit` | `medevac` (case-insensitive)
- `x`, `y`   floats, both bounded to [-5.0, +5.0] by `Coords`
- `priority` `low` | `med` | `high` (case-insensitive)
- `persons`  optional int, defaults to 0

Examples accepted by the parser unit tests:

```
heli 1.0 1.0 high
medevac 0 0 low 2
ffunit -3.5 4.2 med
HELI 2 -2 HIGH
```

`?` and `help` print the grammar reminder. EOF (Ctrl-D on a tty,
end-of-stream from `StringIO` in tests) exits the loop with code 0.

## `@mesh.agent` is NOT used (D-30 confirmation)

Verified by `pytest` source-text gates and by manual `grep`:

```
$ grep -E "@mesh\.agent\(|AgentSpec\(" demos/wildfire/world/firefighter.py
(no matches)
```

The CLI imports `AgentMesh` for the connection-and-call path only. It
imports `MeshError` from `openagentmesh._errors` to catch dispatch
failures. It does NOT import `AgentSpec`. There is no `subject_source`
or `kv_source` call. There is no `mesh.subscribe` or briefing-feed
subscription. The CLI is exactly the "plain caller process" that
`km/specs/wildfire/firefighter.md` and decision D-30 specify.

## Deviations from Plan

None. The plan executed exactly as written. The two trivial in-loop
docstring rewrites (replacing literal `Tasker` and `mesh.briefing` with
descriptive prose so the source-text gates stay clean) were applied
during the GREEN phase before the Task 1 commit, not as deviations.

## Hand-off note for Phase 3

Phase 3 will retrofit a `--nl` flag (default true) that adds the NL
translation hop in front of `mesh.call`. The typed path shipped in this
plan stays accessible behind a `--typed` flag (or, equivalently, by
disabling the default `--nl` with `--no-nl`). Concrete hand-off:

1. Phase 3 will introduce a translator agent (name TBD) that accepts a
   request shape carrying free-text + operator_id and returns a typed
   `TaskCommand` whose `target_fleet` is one of `heli|ffunit|medevac`.
2. The current `repl()` reads exactly one line, parses it, dispatches.
   Phase 3 inserts a translation step between the read and the parse:
   if the line does not look like the typed grammar, route it through
   the translator first; on success, hand the resulting `TaskCommand`
   to a small adapter that constructs the same `DispatchOrder` shape
   this plan already builds, then call the same dispatch path.
3. The audit pubsub (`FirefighterIntent` per `firefighter.md`) is also
   deferred to Phase 3 alongside the translator -- it lands when the NL
   surface starts producing free-text worth auditing.

The split between the pure helpers and the I/O-bearing `repl()` is
designed for this addition: Phase 3 only touches the loop body between
read and parse; the helpers and the dispatch tail can stay as is.

## Threat surface scan

No new network endpoints, auth paths, file access patterns, or schema
changes at trust boundaries beyond what the plan's threat model already
covers. T-02-04-01 (parser robustness) is mitigated -- `parse_dispatch_line`
catches every parse failure as `ValueError`, the REPL catches that
`ValueError` and prints to stderr without crashing. T-02-04-02
(operator_id is unauthenticated string) is accepted per the plan and
pushes to a future enterprise ADR. T-02-04-03 (dispatch lines logged to
stdout) is accepted -- the localhost demo is not a privacy-sensitive
surface; Phase 3 will add an audit pubsub when the translator arrives.

## Self-Check: PASSED

- `demos/wildfire/world/firefighter.py` exists, line count: 368.
- `tests/wildfire/unit/test_firefighter_cli.py` exists, 40 tests.
- Commits in `git log`:
  - `86e35ac` test(02-04): firefighter CLI tests -- parser, source-text gates, REPL stubs
  - `22ab81b` feat(02-04): firefighter CLI helpers + grammar (Task 1)
  - `e620706` feat(02-04): firefighter REPL loop + live mesh.call dispatch (Task 2)
- `uv run pytest tests/wildfire/unit -x -q` -> 192 passed (40 of these are this plan's).
- `uv run python -c "from demos.wildfire.world.firefighter import main; assert callable(main)"` -> exit 0.
- All 8 plan-level verification invariants pass (parse helper count, channel routing presence, no decorator, no AgentSpec, no sources, no `mesh.subscribe`, no briefing reference, no dropped artefacts, no aspirational kwargs).
