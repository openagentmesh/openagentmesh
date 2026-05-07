# ADR-0056: OAM Admin UI

## Status

spec

## Context

OAM has a CLI (`oam`) for operator inspection and invocation, but it is text-only and not suited for exploratory or interactive work. There is no visual interface for browsing registered agents, understanding their contracts, invoking them with typed data, or watching live mesh traffic.

Existing NATS tooling (Surveyor, nats-top, NATS CLI) covers the NATS layer but is blind to OAM semantics: agent contracts, capability types, typed payloads, invocation history. The OAM admin UI is the semantic layer on top.

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
$ oam mesh up         # start the mesh as usual
$ oam ui              # start the admin UI on http://localhost:4223
$ oam ui --port 8080  # custom port
```

### Python package

The UI is an optional install extra:

```bash
pip install "openagentmesh[ui]"
```

This adds `fastapi` and `uvicorn` as runtime dependencies. The compiled frontend assets are bundled into the package under `src/openagentmesh/_ui_assets/` and served by FastAPI as static files. Users need no Node.js at runtime.

### Backend

FastAPI, served by `uvicorn`. Translates HTTP/WebSocket to AgentMesh SDK calls. Binds to `localhost` by default; configurable via `--host` flag or `OAM_UI_HOST` env var.

API surface:

```
GET  /api/agents                         # catalog list
GET  /api/agents/{name}/contract         # full contract JSON
POST /api/agents/{name}/call             # invoke (body = payload JSON; response = JSON)
POST /api/agents/{name}/stream           # streaming invoke (body = payload JSON; response = text/event-stream)
GET  /api/events/stream?subject=<pat>    # SSE via EventSource: live event feed
GET  /api/catalog/stream                 # SSE via EventSource: catalog change events
```

### Frontend

React 18 + TypeScript, bundled with Vite. Pre-built assets are checked into the repo under `src/openagentmesh/_ui_assets/` so that `pip install` works without Node.js. The source lives in `ui/` at the repo root and is excluded from the published sdist/wheel (build output only).

**Styling:** Tailwind CSS (utility-first, no design system dependency).

**Schema-driven forms:** `@rjsf/core` (react-jsonschema-form) generates invocation forms from the agent's JSON Schema input contract. No hand-written form code per agent.

**Build pipeline:** Frontend assets are built by CI only -- not committed to the repo. The CI publish job runs `npm run build` in `ui/` then packages the output into the wheel under `src/openagentmesh/_ui_assets/`. Local development runs the Vite dev server (`npm run dev` in `ui/`) proxying API calls to the local FastAPI process; there is no local build step required to work on the UI.

**Real-time:** SSE only. No WebSockets.

- `EventSource` (GET) for: event feed, catalog change notifications.
- Streaming POST (fetch + ReadableStream) for: streaming agent invocations. The client POSTs the payload JSON; the response is `Content-Type: text/event-stream` consumed via `response.body` async iteration. Wire format is identical to SSE; `EventSource` is not used only because it requires GET.

This keeps the entire transport model on standard HTTP with no WebSocket upgrade, reconnection logic, or WS library dependency.

### Screens

**Agent Registry (`/`)**

Table: name, capability icons (invocable / streaming), description (first sentence), status dot (live/unreachable -- liveness from ADR-0016 when implemented, otherwise omitted). Click row to open agent detail.

**Agent Detail (`/agents/:name`)**

Two-panel layout:
- Left: contract viewer (JSON / human-readable toggle). Shows name, description, full input/output schema, capabilities.
- Right: invocation sandbox. `@rjsf` form rendered from input schema. "Call" button for Responder agents; "Stream" button for Streamer agents. Result displayed below as formatted JSON (Call) or streaming text (Stream). Publisher/Watcher agents show output schema and a link to the event feed filtered to their subject.

**Event Feed (`/events`)**

Subject pattern input (pre-populated with `>`). "Subscribe" starts an SSE connection to `/api/events/stream`. Messages appear in a scrolling list: timestamp, subject (coloured by agent prefix), payload (formatted JSON or raw text). "Pause" / "Clear" controls.

## Code sample (DX contract)

```bash
# install with UI extra
pip install "openagentmesh[ui]"

# start a local mesh and the UI
oam mesh up
oam ui
# → Admin UI running at http://localhost:4223
# → Connected to nats://localhost:4222

# or against a remote mesh
OAM_URL=nats://mesh.example.com:4222 oam ui
```

In the browser:
- `http://localhost:4223/` -- agent table
- `http://localhost:4223/agents/translator` -- contract + invocation sandbox
- `http://localhost:4223/events` -- live feed

## Consequences

- Adds `fastapi`, `uvicorn` as optional runtime deps (UI extra only).
- Adds `ui/` directory at repo root with Node.js toolchain (`package.json`, `vite.config.ts`). The built output is gitignored; CI builds and bundles it into the wheel at publish time.
- `src/openagentmesh/_ui_assets/` is populated only during the CI publish job, not in the working tree.
- `oam ui` is added to the CLI surface (ADR-0033 extension, not a new ADR).
- Liveness status indicator on the registry screen depends on ADR-0016; the dot is hidden until that ADR is implemented.
- `@rjsf/core` covers JSON Schema draft-07; OAM contracts use Pydantic v2-generated schemas (draft-2020-12 compatible with draft-07 for common cases). Verify no regressions on schema features actually used (unions, refs).

## Open items

- Decide `oam ui --host 0.0.0.0` security note: should the UI expose mesh write access over the network? Recommend localhost-only default; remote access via SSH tunnel.
- Pagination or virtual scroll on the event feed for high-throughput meshes.
- Auth-aware UI: deferred until the authz ADR lands.
