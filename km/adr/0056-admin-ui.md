# ADR-0056: OAM Admin UI

## Status

spec (amended 2026-05-09)

## Context

OAM has a CLI (`oam`) for operator inspection and invocation, but it is text-only and not suited for exploratory or interactive work. There is no visual interface for browsing registered agents, understanding their contracts, invoking them with typed data, or watching live mesh traffic.

Existing NATS tooling (Surveyor, nats-top, NATS CLI) covers the NATS layer but is blind to OAM semantics: agent contracts, capability types, typed payloads, invocation history. The OAM admin UI is the semantic layer on top.

> **Amendment 2026-05-09** — backend swapped from FastAPI + SSE to a tiny static-asset server with a `nats.ws` browser client. The admin UI is a generic OAM control-plane tool that operators point at any mesh; requiring a FastAPI translator to be deployed alongside breaks "just works against any OAM mesh." The browser becomes a first-class mesh client. The `oam ui` package extra drops `fastapi`/`uvicorn` runtime dependencies. Embedded NATS gains a `websocket {}` listener block. Tooling switches from `npm` to `pnpm`. Wildfire scenario UI (per `km/specs/wildfire/dashboard.md`) keeps FastAPI + WebSocket as the parallel "OAM behind familiar HTTP" demo for backend-heavy devs — two narratives, two stacks, both supported.

### Scope

Three core screens:

1. **Agent Registry**: browse all registered agents, their capabilities, and live status.
2. **Invocation Sandbox**: schema-driven form generated from the agent's input contract; call or stream; display typed result.
3. **Event Feed**: subscribe to any subject pattern (NATS wildcards supported); live scrolling stream with decoded payloads.

Out of scope for this ADR: KV/Object store browser (deferred), observability/traces (Grafana, ADR-0048), permissions/authz (future enterprise ADR).

## Decision

### Deployment

A standalone `oam ui` command. It uses the same mesh URL resolution as all other `oam` commands (`.oam-url` → `OAM_URL` → default `nats://localhost:4222`). The mesh must already be running; `oam ui` does not start NATS.

```bash
$ oam mesh up                       # start the mesh as usual
$ oam ui                            # serve the static admin UI on http://localhost:4223
$ oam ui --port 8080                # custom port
$ oam ui --nats-ws-url ws://...     # override the NATS WebSocket URL exposed to the browser
```

`oam ui` falls back to the next free port if the requested one is occupied; the resolved URL always prints on boot.

### Python package

The UI is an optional install extra:

```bash
pip install "openagentmesh[ui]"
```

The extra adds nothing beyond a stdlib-or-very-thin static-asset server. **No `fastapi` / `uvicorn` runtime dependencies** — the backend is ~30 lines of static-file serving plus a single `GET /config.json` endpoint that returns the NATS WebSocket URL the browser should connect to. The compiled frontend assets ship under `src/openagentmesh/_ui_assets/`. Users need no Node.js at runtime.

### Backend

A tiny static-asset server bound to `localhost` by default; configurable via `--host` flag or `OAM_UI_HOST` env var. Two responsibilities:

- Serve the bundled SPA from `src/openagentmesh/_ui_assets/`.
- Serve `GET /config.json` returning `{ "nats_ws_url": "<url>", ... }`. Default URL mirrors the embedded NATS WebSocket port (e.g., `ws://localhost:4222`); overridable via `--nats-ws-url` flag or `OAM_NATS_WS_URL` env var.

The browser bootstraps by fetching `/config.json` on load, then opens a `nats.ws` connection directly to the NATS WebSocket listener. There is no HTTP API translating between the browser and the mesh; the browser IS a mesh client.

API surface (server side):

```
GET  /                          # SPA index
GET  /assets/...                # bundled SPA static files (JS, CSS, images)
GET  /config.json               # { nats_ws_url, ... } the SPA reads on bootstrap
```

API surface (browser-side, via `nats.ws` to the mesh directly):

```
JetStream KV watch:
  oam.catalog.>                 # agent registry rows + contracts (catalog change push)

Subject subscribe:
  <user-supplied pattern>       # event feed (e.g. mesh.>, mesh.action.>, ...)

Request/reply (mesh.call equivalent):
  mesh.agent.<name>             # invocation sandbox sends here, awaits reply
```

### Embedded NATS

The embedded NATS that `AgentMesh.local()` and `oam mesh up` boot **must enable WebSocket listening** so the browser can connect:

```hocon
websocket {
  port: 4222          # share the standard mesh port; or split via 4223 if needed
  no_tls: true        # localhost dev; remote deployments add tls + cert
}
```

The exact port + sharing strategy is a runtime config detail, not an architectural one. `oam ui --nats-ws-url` overrides it for non-default deployments.

### Frontend

React 18 + TypeScript, bundled with Vite. Pre-built assets are checked into the repo under `src/openagentmesh/_ui_assets/` so that `pip install` works without Node.js. The source lives in `ui/` at the repo root and is excluded from the published sdist/wheel (build output only).

**Styling:** Tailwind CSS (utility-first, no design system dependency).

**Schema-driven forms:** `@rjsf/core` (react-jsonschema-form) generates invocation forms from the agent's JSON Schema input contract. No hand-written form code per agent.

**Mesh client:** `nats.ws` (the official NATS WebSocket client) plus the JetStream extension for KV watch. Browser opens one WebSocket on bootstrap, manages subscriptions and request/reply through it.

**Build pipeline:** Frontend assets are built by CI only -- not committed to the repo. The CI publish job runs `pnpm install && pnpm run build` in `ui/` then packages the output into the wheel under `src/openagentmesh/_ui_assets/`. Local development runs the Vite dev server (`pnpm run dev` in `ui/`); the dev server serves the SPA + `/config.json` directly, so no separate Python backend is needed during UI development. There is no local build step required to work on the UI.

**Tooling:** **pnpm** (replaces npm). Drop-in for the Vite + React setup; faster installs, content-addressable store, smaller `node_modules`. CI uses `corepack enable && pnpm install`. Lockfile: `ui/pnpm-lock.yaml`.

**Real-time:** native NATS over WebSocket via `nats.ws`. JetStream KV watch streams catalog and (optionally) other KV namespaces; subject subscriptions stream the event feed; request/reply runs over the same connection.

This keeps the entire transport on a single WebSocket and a single coordination primitive (NATS). No SSE, no HTTP API translation layer, no separate WebSocket reconnection logic — `nats.ws` handles reconnection natively.

### Screens

**Agent Registry (`/`)**

Table: name, capability icons (invocable / streaming), description (first sentence), status dot (live/unreachable -- liveness from ADR-0016 when implemented, otherwise a heartbeat-derived stand-in). Rows are sourced from a JetStream KV watch on `oam.catalog.>` plus, when relevant, a watch on a fleet-presence namespace (e.g. `wildfire.fleet.>`) for instance counts and liveness. Click row to open agent detail.

**Agent Detail (`/agents/:name`)**

Two-panel layout:
- Left: contract viewer (JSON / human-readable toggle). Shows name, description, full input/output schema, capabilities. Sourced from the catalog KV record.
- Right: invocation sandbox. `@rjsf` form rendered from input schema. "Call" button for Responder agents (browser does request/reply on `mesh.agent.<name>` directly via nats.ws). "Stream" button for Streamer agents (browser handles the multi-message reply pattern). Result displayed below as formatted JSON (Call) or streaming text (Stream). Publisher/Watcher agents show output schema and a link to the event feed filtered to their subject.

**Event Feed (`/events`)**

Subject pattern input (pre-populated with `>`). "Subscribe" opens (or reuses) a `nats.ws` subscription on the supplied pattern. Messages appear in a scrolling list: timestamp, subject (coloured by agent prefix), payload (formatted JSON or raw text). "Pause" / "Clear" controls.

## Code sample (DX contract)

```bash
# install with UI extra
pip install "openagentmesh[ui]"

# start a local mesh and the UI
oam mesh up                      # embedded NATS includes a websocket listener
oam ui
# → Admin UI running at http://localhost:4223
# → Browser will connect to nats://localhost:4222 (WebSocket)

# or against a remote mesh
OAM_URL=nats://mesh.example.com:4222 OAM_NATS_WS_URL=wss://mesh.example.com:4222 oam ui
```

In the browser:
- `http://localhost:4223/` -- agent table
- `http://localhost:4223/agents/translator` -- contract + invocation sandbox
- `http://localhost:4223/events` -- live feed

The browser fetches `/config.json` once on load, then opens a single nats.ws WebSocket against the configured NATS URL and runs all subsequent operations (catalog watch, sandbox request/reply, event feed subscription) over that connection.

## Consequences

- **No `fastapi` / `uvicorn` runtime deps for the admin UI.** Drops two transitive dependency trees from the `[ui]` extra. The static-asset server is ~30 lines of stdlib (or a tiny ASGI app); the work moves to the browser.
- **Embedded NATS gains a `websocket {}` listener** by default. `AgentMesh.local()` and `oam mesh up` need a small config update; users with custom NATS server configs may need to add the block. Documented in the `oam mesh up` help text and migration notes.
- **`nats.ws` becomes a frontend dependency.** Bundle size grows by ~50KB gzipped. JetStream extension adds ~10KB. Acceptable for a control-plane tool.
- Adds `ui/` directory at repo root with Node.js toolchain (`package.json`, `pnpm-lock.yaml`, `vite.config.ts`). The built output is gitignored; CI builds and bundles it into the wheel at publish time.
- `src/openagentmesh/_ui_assets/` is populated only during the CI publish job, not in the working tree. Local-dev guidance: run `pnpm run dev` in `ui/` and let Vite serve the SPA + `/config.json` directly.
- `oam ui` is added to the CLI surface (ADR-0033 extension, not a new ADR).
- Liveness status indicator on the registry screen depends on ADR-0016; until that ships, a heartbeat-derived stand-in works (the admin UI watches a fleet-presence KV namespace if one exists and treats fresh `last_updated` as "alive").
- `@rjsf/core` covers JSON Schema draft-07; OAM contracts use Pydantic v2-generated schemas (draft-2020-12 compatible with draft-07 for common cases). Verify no regressions on schema features actually used (unions, refs).
- **Authz simplifies:** there's no Python backend in the request path. Authz becomes a NATS-level concern (NKEYs, JWTs, per-subject ACLs). Out of v1 admin UI scope; a future enterprise ADR handles it. Until then, `oam ui` binds to `localhost` only.
- **Tooling: npm → pnpm.** Faster installs, smaller `node_modules`, content-addressable store. Drop-in for the Vite + React setup; `package.json` and `vite.config.ts` are unchanged.

## Open items

- Decide `oam ui --host 0.0.0.0` security note: the admin UI exposes mesh write access to anyone who can reach the NATS WebSocket. Recommend localhost-only default; remote access via SSH tunnel or proper NATS auth.
- Pagination or virtual scroll on the event feed for high-throughput meshes.
- Auth-aware UI: deferred until the authz ADR lands.
- Whether the same nats.ws WebSocket port can serve both browser and Python clients, or whether to split (4222 NATS-native, 4223 WebSocket). Defer to the NATS server config; both work.
