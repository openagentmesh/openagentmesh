# ADR-0056: OAM Admin UI

## Status

spec (amended 2026-05-09, 2026-07-18)

## Context

OAM has a CLI (`oam`) for operator inspection and invocation, but it is text-only and not suited for exploratory or interactive work. There is no visual interface for browsing registered agents, understanding their contracts, invoking them with typed data, or watching live mesh traffic.

Existing NATS tooling (Surveyor, nats-top, NATS CLI) covers the NATS layer but is blind to OAM semantics: agent contracts, capability types, typed payloads, invocation history. The OAM admin UI is the semantic layer on top.

> **Amendment 2026-05-09** — backend swapped from FastAPI + SSE to a tiny static-asset server with a `nats.ws` browser client. The admin UI is a generic OAM control-plane tool that operators point at any mesh; requiring a FastAPI translator to be deployed alongside breaks "just works against any OAM mesh." The browser becomes a first-class mesh client. The `oam ui` package extra drops `fastapi`/`uvicorn` runtime dependencies. Embedded NATS gains a `websocket {}` listener block. Tooling switches from `npm` to `pnpm`. Wildfire scenario UI (per `km/specs/wildfire/dashboard.md`) keeps FastAPI + WebSocket as the parallel "OAM behind familiar HTTP" demo for backend-heavy devs — two narratives, two stacks, both supported.

> **Amendment 2026-07-18** — corrections against the shipped repo (Stage 3 landed auth, liveness, observability, and lifecycle gates after this ADR was written):
>
> 1. **The websocket listener cannot share the client port.** `websocket { port: 4222 }` alongside `port: 4222` fails at boot with `bind: address already in use` (verified against nats-server 2.10.24). Defaults become: websocket on **mesh port + 1** (4223 for the default 4222; a free port for `AgentMesh.local()`), and `oam ui` serves the SPA on **4224** (free-port fallback unchanged). The "exact port is a runtime config detail" sentence below is void — the split is structural.
> 2. **KV layout was wrong.** There is no `oam.catalog.>` namespace. Reality (ADR-0013/0014): bucket `mesh-catalog`, single key `catalog` holding the denormalized JSON array of catalog entries — the registry screen watches that one key. Authoritative per-agent contracts live in bucket `mesh-registry`, key = agent name — the detail screen fetches `mesh-registry/<name>`. Subject-level: `$KV.mesh-catalog.catalog`, `$KV.mesh-registry.<name>`.
> 3. **Liveness is real now** (ADR-0016/0040, shipped): the status dot reads the `mesh-instances` bucket (instance → served agents) and subscribes `mesh.death.>` for live transitions. The "heartbeat-derived stand-in" and `wildfire.fleet.>` presence language below is obsolete; there is no heartbeat layer (deferred in ADR-0016 v1).
> 4. **The Watcher shape is retired** (ADR-0055). Capability shapes are Responder / Streamer / Trigger / Publisher / Source-only; the detail screen shows Call for `invocable`, Stream for `streaming`, and contract + event-feed link otherwise. A gated agent (`active_when`) may answer `not_available` — the sandbox surfaces error envelopes as-is, no special casing beyond rendering the taxonomy code.
> 5. **Invocation wire detail** (for the browser client): request/reply on `mesh.agent.<name>` with an `X-Mesh-Request-Id` header; stream replies arrive on the reply inbox with `X-Mesh-Stream-Seq` / `X-Mesh-Stream-End` headers; errors carry `X-Mesh-Status: error` + a taxonomy envelope (see docs/architecture/envelope.md). The browser reimplements this thin slice of the TS SDK rather than depending on `@openagentmesh/sdk` (which targets Node's TCP transport, not nats.ws) — revisit if the TS SDK ever grows a websocket transport.
> 6. **Auth exists now** (ADR-0038). v1 of the UI stays a dev-mesh tool: anonymous connection, localhost-only serving. Against a secured mesh the browser would need a credential the static server would have to hand out via `config.json` — deliberately out of scope; recorded under Open items.
> 7. **Asset shipping contradiction resolved:** the Frontend section said assets are both "checked into the repo" and "built by CI only". CI-built is the decision (as the 2026-05-09 amendment intended): `src/openagentmesh/_ui_assets/` is gitignored, populated by the wheel-build workflow; `oam ui` without assets prints a clear error pointing at `pnpm dev` for source checkouts.
> 8. **Build waves** for the multi-session implementation are tracked in `km/notes/2026-07-18-adr0056-ui-plan.md`.

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
$ oam mesh up                       # start the mesh as usual (websocket listener on 4223)
$ oam ui                            # serve the static admin UI on http://localhost:4224
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
  mesh-catalog / "catalog"      # registry rows (single denormalized key, ADR-0014)
  mesh-registry / <name>        # full contract, fetched on detail view
  mesh-instances / *            # instance -> served agents (liveness, ADR-0016)

Subject subscribe:
  mesh.death.>                  # liveness transitions for the status dot
  <user-supplied pattern>       # event feed (e.g. mesh.>, mesh.agent.>, ...)

Request/reply (mesh.call equivalent):
  mesh.agent.<name>             # invocation sandbox sends here, awaits reply
```

### Embedded NATS

The embedded NATS that `AgentMesh.local()` and `oam mesh up` boot **must enable WebSocket listening** so the browser can connect:

```hocon
websocket {
  port: 4223          # mesh port + 1 — NATS refuses to share the client port (verified)
  no_tls: true        # localhost dev; remote deployments add tls + cert
}
```

`oam ui --nats-ws-url` overrides it for non-default deployments.

### Frontend

React 18 + TypeScript, bundled with Vite. The source lives in `ui/` at the repo root; compiled assets land in `src/openagentmesh/_ui_assets/` (gitignored, built by the wheel-publish CI job) so that `pip install` works without Node.js.

**Styling:** Tailwind CSS (utility-first, no design system dependency).

**Schema-driven forms:** `@rjsf/core` (react-jsonschema-form) generates invocation forms from the agent's JSON Schema input contract. No hand-written form code per agent.

**Mesh client:** `nats.ws` (the official NATS WebSocket client) plus the JetStream extension for KV watch. Browser opens one WebSocket on bootstrap, manages subscriptions and request/reply through it.

**Build pipeline:** Frontend assets are built by CI only -- not committed to the repo. The CI publish job runs `pnpm install && pnpm run build` in `ui/` then packages the output into the wheel under `src/openagentmesh/_ui_assets/`. Local development runs the Vite dev server (`pnpm run dev` in `ui/`); the dev server serves the SPA + `/config.json` directly, so no separate Python backend is needed during UI development. There is no local build step required to work on the UI.

**Tooling:** **pnpm** (replaces npm). Drop-in for the Vite + React setup; faster installs, content-addressable store, smaller `node_modules`. CI uses `corepack enable && pnpm install`. Lockfile: `ui/pnpm-lock.yaml`.

**Real-time:** native NATS over WebSocket via `nats.ws`. JetStream KV watch streams catalog and (optionally) other KV namespaces; subject subscriptions stream the event feed; request/reply runs over the same connection.

This keeps the entire transport on a single WebSocket and a single coordination primitive (NATS). No SSE, no HTTP API translation layer, no separate WebSocket reconnection logic — `nats.ws` handles reconnection natively.

### Screens

**Agent Registry (`/`)**

Table: name, capability icons (invocable / streaming), description (first sentence), status dot (live/unreachable — from the `mesh-instances` bucket plus `mesh.death.>` subscriptions, ADR-0016). Rows are sourced from a JetStream KV watch on the `mesh-catalog` bucket's single `catalog` key (ADR-0014). Click row to open agent detail.

**Agent Detail (`/agents/:name`)**

Two-panel layout:
- Left: contract viewer (JSON / human-readable toggle). Shows name, description, full input/output schema, capabilities. Sourced from the catalog KV record.
- Right: invocation sandbox. `@rjsf` form rendered from input schema. "Call" button for invocable agents (browser does request/reply on `mesh.agent.<name>` directly via nats.ws). "Stream" button for streaming agents (browser handles the multi-message reply pattern). Result displayed below as formatted JSON (Call) or streaming text (Stream). Non-invocable agents (Publisher / Source-only) show output schema and a link to the event feed filtered to their subject.

**Event Feed (`/events`)**

Subject pattern input (pre-populated with `>`). "Subscribe" opens (or reuses) a `nats.ws` subscription on the supplied pattern. Messages appear in a scrolling list: timestamp, subject (coloured by agent prefix), payload (formatted JSON or raw text). "Pause" / "Clear" controls.

## Code sample (DX contract)

```bash
# install with UI extra
pip install "openagentmesh[ui]"

# start a local mesh and the UI
oam mesh up                      # embedded NATS includes a websocket listener on 4223
oam ui
# → Admin UI running at http://localhost:4224
# → Browser will connect to ws://localhost:4223 (NATS WebSocket)

# or against a remote mesh
OAM_URL=nats://mesh.example.com:4222 OAM_NATS_WS_URL=wss://mesh.example.com:4223 oam ui
```

In the browser:
- `http://localhost:4224/` -- agent table
- `http://localhost:4224/agents/translator` -- contract + invocation sandbox
- `http://localhost:4224/events` -- live feed

The browser fetches `/config.json` once on load, then opens a single nats.ws WebSocket against the configured NATS URL and runs all subsequent operations (catalog watch, sandbox request/reply, event feed subscription) over that connection.

## Consequences

- **No `fastapi` / `uvicorn` runtime deps for the admin UI.** Drops two transitive dependency trees from the `[ui]` extra. The static-asset server is ~30 lines of stdlib (or a tiny ASGI app); the work moves to the browser.
- **Embedded NATS gains a `websocket {}` listener** by default. `AgentMesh.local()` and `oam mesh up` need a small config update; users with custom NATS server configs may need to add the block. Documented in the `oam mesh up` help text and migration notes.
- **`nats.ws` becomes a frontend dependency.** Bundle size grows by ~50KB gzipped. JetStream extension adds ~10KB. Acceptable for a control-plane tool.
- Adds `ui/` directory at repo root with Node.js toolchain (`package.json`, `pnpm-lock.yaml`, `vite.config.ts`). The built output is gitignored; CI builds and bundles it into the wheel at publish time.
- `src/openagentmesh/_ui_assets/` is populated only during the CI publish job, not in the working tree. Local-dev guidance: run `pnpm run dev` in `ui/` and let Vite serve the SPA + `/config.json` directly.
- `oam ui` is added to the CLI surface (ADR-0033 extension, not a new ADR).
- Liveness status indicator on the registry screen uses ADR-0016's shipped machinery: the `mesh-instances` KV bucket and `mesh.death.>` notices.
- `@rjsf/core` covers JSON Schema draft-07; OAM contracts use Pydantic v2-generated schemas (draft-2020-12 compatible with draft-07 for common cases). Verify no regressions on schema features actually used (unions, refs).
- **Authz simplifies:** there's no Python backend in the request path. Authz becomes a NATS-level concern (NKEYs, JWTs, per-subject ACLs). Out of v1 admin UI scope; a future enterprise ADR handles it. Until then, `oam ui` binds to `localhost` only.
- **Tooling: npm → pnpm.** Faster installs, smaller `node_modules`, content-addressable store. Drop-in for the Vite + React setup; `package.json` and `vite.config.ts` are unchanged.

## Open items

- Decide `oam ui --host 0.0.0.0` security note: the admin UI exposes mesh write access to anyone who can reach the NATS WebSocket. Recommend localhost-only default; remote access via SSH tunnel or proper NATS auth.
- Pagination or virtual scroll on the event feed for high-throughput meshes.
- Auth-aware UI (ADR-0038 shipped since): the browser would need a credential, and `config.json` handing out creds is a security decision — deferred; v1 targets anonymous dev meshes only.
- ~~Whether the same nats.ws WebSocket port can serve both browser and Python clients~~ — resolved 2026-07-18: NATS refuses to bind websocket on the client port; the split (4222 native / 4223 websocket) is mandatory.
