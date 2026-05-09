---
phase: 01-detection-foundation
plan: 09
subsystem: admin-ui
tags: [admin-ui, react, vite, pnpm, tailwind, nats-ws, jetstream-kv, ADR-0056-amendment, D-13, D-15, D-16, D-17, D-18]

# Dependency graph
requires:
  - phase: 01-detection-foundation
    plan: 08
    provides: "oam ui static-asset server (port 8088) + GET /config.json + EmbeddedNats WebSocket listener (port 4223)"
  - external: "Browser-side NATS v3 client ecosystem (@nats-io/nats-core 3.4.0 with wsconnect, @nats-io/jetstream 3.4.0, @nats-io/kv 3.4.0)"
provides:
  - "ui/ at the worktree root: pnpm + Vite + React 18 + TypeScript + Tailwind source for the OAM admin UI"
  - "ui/src/lib/nats.ts: fetch /config.json, then wsconnect({servers:[cfg.nats_ws_url]}); singleton NatsConnection"
  - "ui/src/lib/catalog.ts: KV watch on bucket mesh-catalog, key 'catalog' (canonical OAM catalog payload as a JSON CatalogEntry array)"
  - "ui/src/lib/fleet.ts: KV watch on bucket mesh-context, prefix 'wildfire.fleet.>' with reader-side liveness (now - last_updated*1000 < 3000 ms per D-10)"
  - "ui/src/components/RegistryTable.tsx: flat agent table (D-13, no channel grouping) with name + capability glyphs + live/total counter + status dot"
  - "ui/src/App.tsx + main.tsx: wires the watchers into the table, re-renders every 1 s so liveness staleness updates without a KV event"
  - "src/openagentmesh/_ui_assets/index.html (built by pnpm run build) per D-18, ready for oam ui to serve"
  - "ui/pnpm-lock.yaml: locked dependency tree using pnpm@9.15.9"
  - ".gitignore extension: ui/node_modules/, ui/dist/, src/openagentmesh/_ui_assets/* with .gitkeep exemption"
affects:
  - 01-10 (orchestrator integration: orchestrator already passes --nats-ws-url to oam ui per plan 03; the bundle now exists so oam ui will not exit 2 with the missing-assets error)
  - 01-11 (cookbook recipe + integration test: the round-trip http://127.0.0.1:8088/ -> _ui_assets/index.html -> /config.json -> ws://127.0.0.1:4223 -> KV watches now has working browser-side code; admin UI registry assertion is reachable)
  - "Future: any additional admin UI screen (agent detail, event feed) reuses watchCatalog/watchFleet patterns and the lib/ structure"

# Tech tracking
tech-stack:
  added:
    - "pnpm 9.15.9 (UI package manager per D-17)"
    - "Vite 5.4.21 (UI bundler per D-17, output goes to src/openagentmesh/_ui_assets/ per D-18)"
    - "React 18.3.1 + react-dom 18.3.1 (admin UI framework per ADR-0056)"
    - "TypeScript 5.9.3 (UI types)"
    - "Tailwind CSS 3.4.19 + PostCSS 8.5.14 + Autoprefixer 10.5.0 (UI styling per ADR-0056)"
    - "@nats-io/nats-core 3.4.0 (browser NATS client via wsconnect; replaces deprecated nats.ws@1.x)"
    - "@nats-io/jetstream 3.4.0 (browser JetStream client)"
    - "@nats-io/kv 3.4.0 (browser KV watcher API)"
    - "@vitejs/plugin-react 4.7.0 (Vite React HMR support)"
    - "@types/react 18.3.28 + @types/react-dom 18.3.7 (TypeScript types)"
  patterns:
    - "Browser bootstrap: fetch('/config.json') first, then open NATS WebSocket. Honors ADR-0056 amendment (D-16): the static server is the URL discovery layer, the browser is a first-class mesh client."
    - "Singleton NatsConnection in ui/src/lib/nats.ts: one connection per browser tab, reused by both watchers. Avoids per-watcher reconnects."
    - "JetStream KV watcher pattern: open the bucket, kv.watch({key: ...}), iterate the AsyncIterator, JSON-decode the payload. Same shape across catalog and fleet watchers; the only difference is the key (catalog scalar vs wildfire.fleet.> wildcard)."
    - "Reader-side liveness (D-10): the browser computes liveness from now - last_updated*1000 < 3000 ms. No server-side TTL, no sweeper agent. A 1 s setInterval forces a re-render so an agent going stale flips its status dot even between KV events."
    - "Flat instance counter: derive zone+type from agent name via name.split('.', 2), then count fleet keys whose dotted segments [2][3] match. Channel grouping is deferred to Phase 3 per D-13."

key-files:
  created:
    - "ui/package.json"
    - "ui/pnpm-lock.yaml"
    - "ui/tsconfig.json"
    - "ui/vite.config.ts"
    - "ui/postcss.config.js"
    - "ui/tailwind.config.js"
    - "ui/index.html"
    - "ui/src/index.css"
    - "ui/src/main.tsx"
    - "ui/src/App.tsx"
    - "ui/src/lib/nats.ts"
    - "ui/src/lib/catalog.ts"
    - "ui/src/lib/fleet.ts"
    - "ui/src/components/RegistryTable.tsx"
    - "src/openagentmesh/_ui_assets/.gitkeep"
  modified:
    - ".gitignore"
  build-output (gitignored):
    - "src/openagentmesh/_ui_assets/index.html"
    - "src/openagentmesh/_ui_assets/assets/index-<hash>.css"
    - "src/openagentmesh/_ui_assets/assets/index-<hash>.js"

key-decisions:
  - "Drop nats.ws@1.30.3 in favor of @nats-io/nats-core 3.4.0 wsconnect. The plan listed nats.ws as the browser client, but pnpm install pulled in @nats-io/{kv,jetstream}@3.4.0 (current as of 2026-05-08), and those v3 packages depend on @nats-io/nats-core's NatsConnection type which is structurally incompatible with the legacy nats.ws@1.30.3 NatsConnection (missing setServers/getServers methods). nats.ws is also npm-deprecated. The v3 ecosystem replacement is wsconnect from @nats-io/nats-core itself; same shape, same bootstrap, type-compatible with the v3 KV/JetStream packages."
  - "vite.config.ts uses emptyOutDir: false (deviation from plan default emptyOutDir: true). The tracked .gitkeep at src/openagentmesh/_ui_assets/.gitkeep would otherwise be wiped on every build, leaving the directory in an inconsistent git state. Stale build artifacts are still gitignored, so the cleanup loss is zero."
  - "Reader-side liveness implementation: a 1 s setInterval triggers a tick state update so the table re-renders even when no KV event has arrived. Without this, an agent that simply stopped heartbeating would keep its 🟢 dot until something else updated the row -- the staleness check would never fire."
  - "Status dot logic: 🟢 (any live instance), 🟡 (registered + has fleet records but every record is stale), ⚫ (no fleet record at all). The third state covers agents that legitimately do not heartbeat into wildfire.fleet.>; in Phase 1 every fleet agent does, so ⚫ would only show for stragglers (e.g. a future briefer with no fleet presence)."
  - "Instance grouping uses dot-segment indexing rather than channel-prefix grouping. Phase 1 = flat list per D-13; the [2][3] segment match is just there to count fleet rows under wildfire.fleet.<zone>.<type>.<instance_id> against the catalog name <zone>.<type>. Channel-prefix grouping (Phase 3) would replace this with a Map<channel_prefix, AgentRow[]> render."

patterns-established:
  - "ui/src/lib/<topic>.ts: one file per KV-backed topic the browser observes. Each exports an async watch<Topic>(onUpdate) that returns a stop function. New screens add new lib/<topic>.ts files; the App component composes them."
  - "Zero per-screen NATS plumbing: lib/nats.ts owns the singleton; lib/<topic>.ts files only ever call ensureConnection() and open their KV bucket. Adding a third watcher (events, contracts, anything else) is a copy-paste of catalog.ts."
  - "Three-file extension recipe for a new screen (per the plan output spec): (1) ui/src/lib/<topic>.ts watcher, (2) ui/src/components/<Screen>.tsx component, (3) wire it into ui/src/App.tsx (or a Router when the admin UI grows past one screen)."

requirements-completed: [ADM-01]

# Metrics
duration: ~4min
completed: 2026-05-09
---

# Phase 1 Plan 09: Admin UI MVP (React + TypeScript + Vite + Tailwind, browser-side NATS) Summary

**The OpenAgentMesh admin UI MVP lands as a static React bundle. The browser is a first-class mesh client: it bootstraps via `GET /config.json` from `oam ui` (port 8088), opens a NATS WebSocket connection (port 4223 by default) using `@nats-io/nats-core` `wsconnect`, watches `mesh-catalog` (key `catalog`) and `mesh-context` (prefix `wildfire.fleet.>`) JetStream KV streams, and renders a flat agent table (per D-13) with reader-side liveness (per D-10).**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-09T00:42:23Z
- **Completed:** 2026-05-09T00:46:38Z
- **Tasks:** 2 (both `auto`)
- **Files created:** 14 source files + 1 `.gitkeep`
- **Files modified:** 1 (`.gitignore`)
- **Build output:** `src/openagentmesh/_ui_assets/{index.html,assets/...}` (gitignored)

## Two-port mental model

This is the canonical port map for the admin UI flow. Plan 11 cookbook + integration test cross-checks against this.

| Port | Component                              | Owner                                     | Protocol |
|------|----------------------------------------|-------------------------------------------|----------|
| 8088 | `oam ui` HTTP server                   | `src/openagentmesh/cli/ui.py` (plan 08)   | HTTP     |
| 4223 | Embedded NATS WebSocket listener       | `EmbeddedNats` (plan 08) / orchestrator   | WS       |

The browser fetches `http://127.0.0.1:8088/` (HTML + assets) and `http://127.0.0.1:8088/config.json` (URL discovery), then opens a separate connection to `ws://127.0.0.1:4223`. The two ports are deliberately distinct so neither path is mistakable for the other; `oam ui` itself never speaks NATS.

## Boot trace (verified via smoke test)

```
1. user runs:   uv run oam ui --port 8088 --nats-ws-url ws://127.0.0.1:4223
2. browser GET  http://127.0.0.1:8088/                       -> _ui_assets/index.html (plan 09 build output)
3. browser GET  http://127.0.0.1:8088/config.json            -> {"nats_ws_url": "ws://127.0.0.1:4223"}
4. browser:     wsconnect({servers:["ws://127.0.0.1:4223"]}) -> singleton NatsConnection
5. browser:     kv.open("mesh-catalog").watch({key:"catalog"})    -> CatalogEntry[] payload
6. browser:     kv.open("mesh-context").watch({key:"wildfire.fleet.>"}) -> FleetMember per key
7. table renders: one row per catalog entry; live/total derived from fleet keys.
```

The smoke test in this plan only verified steps 1-3 (the static-asset path; KV is exercised end-to-end by plan 11's integration test).

## Resolved npm package versions

| Package                        | Plan asked for | Resolved |
|--------------------------------|----------------|----------|
| `react`                        | `^18.3.0`      | `18.3.1` |
| `react-dom`                    | `^18.3.0`      | `18.3.1` |
| `@nats-io/nats-core`           | (deviation)    | `3.4.0`  |
| `@nats-io/jetstream`           | `^3.0.0`       | `3.4.0`  |
| `@nats-io/kv`                  | `^3.0.0`       | `3.4.0`  |
| `typescript`                   | `^5.5.0`       | `5.9.3`  |
| `vite`                         | `^5.4.0`       | `5.4.21` |
| `tailwindcss`                  | `^3.4.0`       | `3.4.19` |
| `autoprefixer`                 | `^10.4.0`      | `10.5.0` |
| `postcss`                      | `^8.4.0`       | `8.5.14` |
| `@vitejs/plugin-react`         | `^4.3.0`       | `4.7.0`  |
| `@types/react`                 | `^18.3.0`      | `18.3.28` |
| `@types/react-dom`             | `^18.3.0`      | `18.3.7` |
| ~~`nats.ws`~~                  | `^1.30.3`      | dropped (see Deviations) |

## KV bucket / key contract (for plan 11 cross-check)

| Browser-side watcher            | Bucket          | Key shape                       | Payload (decoded)                   |
|---------------------------------|-----------------|---------------------------------|-------------------------------------|
| `watchCatalog` (`catalog.ts`)   | `mesh-catalog`  | `catalog` (scalar)              | `CatalogEntry[]`                    |
| `watchFleet` (`fleet.ts`)       | `mesh-context`  | `wildfire.fleet.>` (wildcard)   | `FleetMember` per key               |

Bucket names match `src/openagentmesh/_mesh.py:46-50` (`_CATALOG_BUCKET = "mesh-catalog"`, `_CONTEXT_BUCKET = "mesh-context"`, `_CATALOG_KEY = "catalog"`).

## How to extend (three-file recipe per the plan output spec)

To add a new screen later:

1. **Watcher:** `ui/src/lib/<topic>.ts` -- copy `catalog.ts` or `fleet.ts`, swap bucket + key, swap payload type.
2. **Component:** `ui/src/components/<Screen>.tsx` -- consumes the watcher's data via props.
3. **Wire-up:** add `useEffect` + state to `ui/src/App.tsx` (or introduce a Router when there is more than one screen).

Each watcher exports `watch<Topic>(onUpdate): Promise<() => void>`; `App.tsx` already shows the cleanup pattern.

## Verification

Plan-level `<verification>`:

1. `cd ui && pnpm run build` -> exit 0; produces `src/openagentmesh/_ui_assets/index.html` + `assets/`. **PASS**
2. `grep -F "mesh-catalog" ui/src/lib/catalog.ts` -> 2 matches. **PASS**
3. `grep -F "wildfire.fleet" ui/src/lib/fleet.ts` -> 3 matches. **PASS**
4. `grep -F "_ui_assets/" .gitignore` -> 2 matches (the wildcard + the gitkeep exemption). **PASS**
5. `oam ui --port 18088 --nats-ws-url ws://127.0.0.1:4223 &; curl http://127.0.0.1:18088/config.json` -> `{"nats_ws_url": "ws://127.0.0.1:4223"}`. **PASS**

Per-task `<verify>`:

- **Task 1:** All scaffold files exist (`ui/package.json`, `ui/vite.config.ts`, `ui/tsconfig.json`, `ui/index.html`, `ui/src/index.css`, `ui/postcss.config.js`, `ui/tailwind.config.js`, `src/openagentmesh/_ui_assets/.gitkeep`). `.gitignore` excludes `ui/node_modules/` and `src/openagentmesh/_ui_assets/*` while exempting `.gitkeep`. `vite.config.ts` has `build.outDir = "../src/openagentmesh/_ui_assets"`. No `package-lock.json` / `npm-shrinkwrap.json`. **PASS**
- **Task 2:** All React source files exist; `ui/src/lib/nats.ts` calls `fetch("/config.json")` then `wsconnect({servers:[cfg.nats_ws_url]})`; `ui/src/lib/catalog.ts` opens KV bucket `mesh-catalog` and watches key `catalog`; `ui/src/lib/fleet.ts` opens KV bucket `mesh-context` and watches `wildfire.fleet.>` with `LIVENESS_STALENESS_MS = 3_000`; `RegistryTable` renders one row per catalog entry; `pnpm run build` produces `src/openagentmesh/_ui_assets/index.html`. **PASS**

Smoke test (post-build):

- `oam ui --port 18088 --nats-ws-url ws://127.0.0.1:4223` -> "Admin UI running at http://127.0.0.1:18088".
- `curl http://127.0.0.1:18088/config.json` -> `{"nats_ws_url": "ws://127.0.0.1:4223"}`.
- `curl http://127.0.0.1:18088/index.html` -> the Vite-built `<!doctype html>...` shell.
- `curl http://127.0.0.1:18088/agents/foo` -> 200 (SPA history-mode fallback to index.html).
- `curl http://127.0.0.1:18088/assets/missing.js` -> 404 (asset paths do not fall back).

## Notes for downstream consumers

- **Plan 10 (orchestrator integration):** the orchestrator's existing `--nats-ws-url ws://127.0.0.1:4223` argument is already correct; no change needed. The orchestrator must run `cd ui && pnpm install && pnpm run build` once before the first orchestrator boot, otherwise `oam ui` will exit 2 with the missing-assets message. (Plan 11 cookbook documents this step.)
- **Plan 11 (cookbook recipe + integration test):** the recipe should mention `pnpm install && pnpm run build` once as a setup step, then `oam ui` (defaults). The integration test asserts `curl http://127.0.0.1:8088/config.json` returns the configured `nats_ws_url`; the registry round-trip needs `pnpm run build` to have populated `_ui_assets/` first.
- **Liveness window tuning:** if the demo wants faster row-disappearance after a kill, lower `LIVENESS_STALENESS_MS` in `ui/src/lib/fleet.ts`. Current 3_000 ms = "3 missed 1 Hz heartbeats" per D-10.
- **Channel grouping (Phase 3):** when ADM-01a lands, replace the flat `<tbody>` in `RegistryTable` with a `Map<channel_prefix, AgentRow[]>` render; everything else (catalog watcher, fleet watcher, instance counter) stays the same.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Replaced `nats.ws@1.30.3` with `@nats-io/nats-core@3.4.0` (`wsconnect`)**
- **Found during:** Task 2 build (`tsc && vite build`).
- **Issue:** `pnpm install` resolved `@nats-io/jetstream@3.4.0` and `@nats-io/kv@3.4.0` (current 2026-05 majors per the plan's `^3.0.0` spec). Those v3 packages internally depend on `@nats-io/nats-core@3.4.0` and its `NatsConnection` type. The legacy `nats.ws@1.30.3` ships its own `NatsConnection` type (from `nats-base-client`) which is missing `setServers`/`getServers` and is structurally incompatible. `tsc` failed:
  ```
  src/lib/catalog.ts:20:24 error TS2345
  Type 'NatsConnection' (from nats.ws) is missing the following properties
  from type 'NatsConnection' (from @nats-io/nats-core): setServers, getServers
  ```
  `nats.ws` is also npm-deprecated. The plan's note (line 151) anticipated this kind of API shift and asked the executor to "follow the package README and adjust the import shapes" while keeping the same data shape, which is what happened.
- **Fix:** Replace `nats.ws` dependency with `@nats-io/nats-core@^3.4.0`. Replace `import { connect } from "nats.ws"` with `import { wsconnect } from "@nats-io/nats-core"` in `ui/src/lib/nats.ts`. Same call shape (`wsconnect({ servers: [...] })`), same `NatsConnection` return type, but now type-compatible with `@nats-io/{kv,jetstream}` v3.
- **Files modified:** `ui/package.json`, `ui/src/lib/nats.ts`, `ui/pnpm-lock.yaml` (regenerated).
- **Commit:** Folded into commit `22f4884` (Task 2). Both the plan-listed `nats.ws` line in `package.json` and the legacy import in `nats.ts` were rewritten before commit.

**2. [Rule 1 - Bug] Set `vite.config.ts` `emptyOutDir: false` to preserve the tracked `.gitkeep`**
- **Found during:** First `pnpm run build` (Task 2).
- **Issue:** Vite's default for `outDir` outside the project root is `emptyOutDir: true` (and the plan explicitly set it to `true`). That wiped `src/openagentmesh/_ui_assets/.gitkeep`, which the `.gitignore` exemption depends on -- without it, the directory disappears from git on every build, and the gitignore wildcard `_ui_assets/*` no longer applies because the directory has no content.
- **Fix:** Set `emptyOutDir: false` in `ui/vite.config.ts` and recreate the `.gitkeep`. Stale build artifacts are still gitignored, so the cleanup loss is zero. A Vite plugin could be written later that wipes `assets/*` while preserving `.gitkeep`, but that is over-engineering for Phase 1.
- **Files modified:** `ui/vite.config.ts`, `src/openagentmesh/_ui_assets/.gitkeep` (recreated).
- **Commit:** Folded into commit `22f4884` (Task 2).

### Authentication gates

None.

### Architectural changes (Rule 4)

None. The deviations above are mechanical fixes that preserve the plan's intent.

## Threat Flags

None new. The plan's threat register covers:

- **T-01-09-01** (Information Disclosure: nats.ws bundle exposes WS connection details) -- mitigated by Phase 1 binding to localhost (oam ui defaults to `127.0.0.1`, embedded NATS WS too). The browser code only ever reads the URL `oam ui` hands it, and only ever connects to that URL.
- **T-01-09-02** (Tampering: forged FleetMemberState JSON in KV) -- accepted; both `catalog.ts` and `fleet.ts` parse inside try/catch and silently drop malformed payloads. A bad value cannot crash the registry.
- **T-01-09-03** (Denial of Service: catalog payload growth) -- accepted; Phase 1 has 5 catalog entries, the catalog payload is well under any practical browser memory limit.

The implementation introduces no surface beyond what the plan's threat model already enumerated. Specifically:

- No new network endpoints (browser only fetches `/config.json` from same-origin and opens `wsconnect` to the URL it received).
- No auth path (Phase 1 is unauthenticated localhost; remote auth is gated by a future enterprise ADR per ADR-0056).
- No file access patterns (the browser does no FS access).
- No schema changes at trust boundaries (catalog payload shape matches `_models.py:CatalogEntry`; fleet payload shape matches `km/specs/wildfire/contracts.md:FleetMemberState`).

## Self-Check: PASSED

- File `ui/package.json`: FOUND
- File `ui/pnpm-lock.yaml`: FOUND
- File `ui/tsconfig.json`: FOUND
- File `ui/vite.config.ts`: FOUND
- File `ui/postcss.config.js`: FOUND
- File `ui/tailwind.config.js`: FOUND
- File `ui/index.html`: FOUND
- File `ui/src/index.css`: FOUND
- File `ui/src/main.tsx`: FOUND
- File `ui/src/App.tsx`: FOUND
- File `ui/src/lib/nats.ts`: FOUND
- File `ui/src/lib/catalog.ts`: FOUND
- File `ui/src/lib/fleet.ts`: FOUND
- File `ui/src/components/RegistryTable.tsx`: FOUND
- File `src/openagentmesh/_ui_assets/.gitkeep`: FOUND
- File `src/openagentmesh/_ui_assets/index.html`: FOUND (build output, gitignored)
- File `.gitignore` extension: FOUND (4 new lines under "Frontend build artifacts (D-18)")
- Commit `75207ef` (Task 1): FOUND in `git log` -- `feat(01-09): ui/ scaffolding (pnpm + Vite + React + Tailwind)`
- Commit `22f4884` (Task 2): FOUND in `git log` -- `feat(01-09): admin UI React app, NATS bootstrap, and KV-backed registry table`
