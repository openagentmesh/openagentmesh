# Phase 1 -- Plan 01-11: Human-verify checklist (Task 2)

**Plan:** `.planning/phases/01-detection-foundation/01-11-PLAN.md` Task 2
**Plan source-of-truth:** `/Users/luca/dev/ai/openagentmesh/.worktrees/wildfire-demo/.planning/phases/01-detection-foundation/01-11-PLAN.md`
**Type:** `checkpoint:human-verify` (blocking gate)
**Automated test:** Task 1 (`tests/wildfire/integration/test_phase1_cascade.py`) **PASSED** locally in ~15 s.

This file is the parking lot for everything pytest cannot assert: visual liveness flicker on process kill, browser actually rendering the registry, instance count badges, and the cascade "feeling right" for a recording.

---

## What was built

Phase 1 multi-process boot. `python -m demos.wildfire` starts:

- Embedded NATS with WebSocket listener on `:4223` and standard listener on `:4222`.
- 11 fleet child processes:
  - `fire-sim` x 1
  - `high-alt.uav` x 1
  - `low-alt.drone` x 5
  - `low-alt.heli` x 1
  - `ground.ffunit` x 3
- `oam ui` admin UI server (HTTP on `:8088`).
- The spawn CLI (`python -m demos.wildfire.world.spawn x y temp`) writes a `CellState` directly to KV (per A-06 amendment).
- The admin UI shows a flat list of agents with live instance counts and reader-side liveness (3 s staleness cutoff per D-10).

---

## Port mental model (don't drift)

| Port | Role | Hit by |
| ---- | ---- | ------ |
| `4222` | embedded NATS standard listener | Fleet processes, side-channel test client, spawn CLI |
| `4223` | embedded NATS WebSocket listener | Browser via `nats.ws` (the React app) |
| `8088` | `oam ui` HTTP server | Browser, integration test (`/config.json`, `/`) |
| `8222` | NATS monitoring HTTP | Operator, optional |

`8088` is **deliberately distinct** from `4223`. `4223` is NATS WebSocket; serving HTML there would collide with NATS protocol.

---

## How to verify

Open two terminals at the worktree root.

### Terminal 1 -- boot the demo

```bash
cd /Users/luca/dev/ai/openagentmesh/.worktrees/wildfire-demo

# (one-time, if src/openagentmesh/_ui_assets/index.html is missing)
cd ui && corepack enable && pnpm install && pnpm run build && cd ..

uv run python -m demos.wildfire
```

**Expected stdout** (interleaved, prefix-tagged, honcho-style):

- `[orchestrator] embedded NATS at nats://127.0.0.1:4222 (ws on :4223)`
- `[orchestrator] spawned [fire-sim-0] (pid=...)`, `[uav-0]`, `[drone-0]` ... `[drone-4]`, `[heli-0]`, `[ffunit-0]` ... `[ffunit-2]`
- `[orchestrator] admin UI at http://127.0.0.1:8088`
- `[orchestrator] ready -- Ctrl+C to stop`
- Steady 1 Hz heartbeat lines from every fleet member after boot
- No tracebacks beyond transient connect-retry hiccups during the first ~2 s

### Browser -- open `http://127.0.0.1:8088/`

Expected:

- Heading "OpenAgentMesh Admin"
- Subtitle "Registry -- flat list (5 agents)"
- A table with 5 rows: `fire-sim`, `high-alt.uav`, `low-alt.drone`, `low-alt.heli`, `ground.ffunit`
- **Capability column:**
  - `fire-sim` shows nothing (Watcher)
  - `high-alt.uav` shows nothing (Watcher)
  - `low-alt.drone` shows nothing (Watcher)
  - `low-alt.heli` shows the invocable badge
  - `ground.ffunit` shows the invocable badge
- **Instances column:**
  - `fire-sim` shows `0/0` (no fleet record per plan 04)
  - `high-alt.uav` shows live `1/1`
  - `low-alt.drone` shows live `5/5`
  - `low-alt.heli` shows live `1/1`
  - `ground.ffunit` shows live `3/3`
- 9 live instances in fleet records, plus fire-sim in catalog only -- **5 catalog rows total, ~10 process heartbeats** (1 + 5 + 1 + 3).
- DevTools -> Network -> WS shows the browser opened a NATS WebSocket connection to `ws://127.0.0.1:4223`. Two ports, two roles: 8088 = HTML/JS/CSS/config.json, 4223 = NATS WS.

### Terminal 2 -- drive the cascade

```bash
cd /Users/luca/dev/ai/openagentmesh/.worktrees/wildfire-demo
NATS_URL=nats://127.0.0.1:4222 uv run python -m demos.wildfire.world.spawn 0 0 600
```

Expected output:

- `wrote wildfire.world.cell.25.25 temp=600.0 by=<hex>`

Within ~5 s, Terminal 1 should show:

- `[uav-0] detected: <id> @ (...) temp=... conf=...` (UAV writes a pending detection)
- One `[drone-N]` line: `surveyed detection <id>` (CAS election + survey complete)

### Chaos verification (D-10 reader-side liveness)

From a third terminal, kill any one drone process:

```bash
# Find a drone PID:
pgrep -af "demos.wildfire.fleet.drone"
# Kill it:
kill -TERM <pid>
```

After ~3 s, the admin UI should show `low-alt.drone` instances drop from `5/5` to `4/5` (or `4/4`, depending on exact teardown semantics). The row should not disappear (heli/ffunit do not die, only one drone exited), but the count should reflect the missing heartbeat.

---

## Acceptance checklist

Tick each item or describe what you saw:

- [ ] All 11 child processes start without errors (1 fire-sim + 1 uav + 5 drones + 1 heli + 3 ffunits)
- [ ] `[orchestrator] admin UI at http://127.0.0.1:8088` line appears
- [ ] Admin UI loads at `http://127.0.0.1:8088/`
- [ ] Browser DevTools shows a WS connection to `ws://127.0.0.1:4223`
- [ ] All 5 catalog rows visible (`fire-sim`, `high-alt.uav`, `low-alt.drone`, `low-alt.heli`, `ground.ffunit`)
- [ ] Instance counts show `0/0` (fire-sim), `1/1` (uav), `5/5` (drone), `1/1` (heli), `3/3` (ffunit)
- [ ] Spawn CLI triggers a UAV detection AND a drone survey within ~5 s (Terminal 1 logs)
- [ ] Killing a single drone process makes the live count drop within ~3 s
- [ ] Ctrl+C on the orchestrator cleanly tears down NATS + every child (no zombie processes)

If any item fails, describe what you saw -- it becomes the gap-closure input for `/gsd-plan-phase --gaps`.

---

## What the automated test already proved

`tests/wildfire/integration/test_phase1_cascade.py` (Task 1 of this plan) ran **green locally** in ~15 s on `2026-05-09T01:09Z`. It asserted, end-to-end:

- The 5 expected catalog names appear (`fire-sim`, `high-alt.uav`, `low-alt.drone`, `low-alt.heli`, `ground.ffunit`).
- At least 10 fleet heartbeat keys exist (`mesh.kv.list("wildfire.fleet.>")`).
- At least one detection reaches `state="surveyed"` within 60 s (`mesh.kv.list("wildfire.detection.>")`).
- `GET http://127.0.0.1:8088/config.json` returns JSON with `nats_ws_url`.
- `GET http://127.0.0.1:8088/` returns HTML containing an `id="root"` mount or "openagentmesh" branding.
- Cleanup terminates the orchestrator process group cleanly (no leftover children after the test).

This human-verify checkpoint exists to catch what pytest cannot:

- Browser actually rendering the registry (not just `index.html` returning HTML).
- Visual flicker / row-count update when a process dies (timing feel, not just KV key disappearance).
- The cascade "looking right" for a future Phase 5 recording.

---

## Resume signal

When ready, respond to the orchestrator with one of:

- `approved` -- if every checklist item ticks
- `<describe issue>` -- if any item fails (becomes the input for `/gsd-plan-phase --gaps`)
