# Admin UI

You want to see the mesh: which agents are registered, whether they are
alive, what their contracts look like, and what is actually flowing over the
wire — and invoke one with typed data without writing a script. The admin UI
is a browser app for exactly that: an agent registry, an invocation sandbox,
and a live event feed.

## Start it

Release wheels bundle the compiled UI; nothing beyond `pip install
openagentmesh` is needed. Start a mesh, then serve the UI:

```bash
oam mesh up      # embedded NATS opens a WebSocket listener on mesh port + 1
oam ui
```

```text
Admin UI running at http://127.0.0.1:4224
Browser will connect to ws://localhost:4223 (NATS WebSocket)
```

Open `http://127.0.0.1:4224` and you are looking at the mesh. If the port is
taken, `oam ui` falls back to the next free one and prints the resolved URL.

To see what `oam ui` would do without starting the server:

```bash
oam ui --check
```

```text
UI assets: .../openagentmesh/_ui_assets
Browser will connect to ws://localhost:4223 (NATS WebSocket)
```

## How it connects

There is no HTTP API between the browser and the mesh. `oam ui` serves two
things: the static app, and `GET /config.json` with the NATS WebSocket URL.
The browser fetches the config once, opens a WebSocket straight to NATS, and
from then on it is a first-class mesh client — catalog watch, request/reply,
subscriptions all run over that one connection.

## The registry

The front page is the agent table: name, capability badges (shape from the
handler, per [contracts](../concepts/contracts.md)), first sentence of the
description, and a status dot. The dot is live when at least one instance of
the agent is connected — it reads the same instance tracking and death
notices as [liveness](../concepts/liveness.md).

One thing to know: on a mesh with a running health monitor (`oam mesh up`
starts one), a crashed agent's row is *removed* — the monitor deregisters it
from the catalog. The gray "offline" dot appears only in the brief window
between the death notice and the catalog cleanup, or on meshes running
without a monitor. Don't expect dead agents to linger gray.

## The invocation sandbox

Click an agent to open its detail screen: the full contract (human-readable
or raw JSON) next to an invocation form generated from the agent's input
schema. Fill it in and **Call** — the reply renders as formatted JSON.
Streaming agents get a **Stream** button instead; chunks render as they
arrive, with a **Stop** to abort mid-stream.

Errors come back as the standard [error envelope](../concepts/errors.md) and
render with the taxonomy code. A [lifecycle-gated](lifecycle-gated-agents.md)
agent whose gate is closed answers `not_available`, exactly as a Python
caller would see it.

## The event feed

The events screen wiretaps any subject pattern. The default `mesh.>` shows
all mesh traffic — invocations, death notices, log events. Subscribe while
agents are working and watch requests scroll by; **Pause** buffers arrivals
(resume flushes them), **Clear** empties the list. The feed keeps the most
recent 500 rows.

Prefer `mesh.>` (or something narrower like `mesh.logs.>`) over a bare `>`:
the UI is itself a mesh client, so a bare `>` taps the UI's own JetStream
API chatter and floods the feed.

## Against a remote mesh

`oam ui` resolves the mesh URL like every other command (`.oam-url` →
`OAM_URL` → localhost default) and assumes the WebSocket listener is on mesh
port + 1. Point the browser elsewhere explicitly when it isn't:

```bash
OAM_URL=nats://mesh.example.com:4222 \
  oam ui --nats-ws-url wss://mesh.example.com:4223
```

The v1 UI connects anonymously — it targets dev meshes. Against a
[secured mesh](secured-mesh.md) the browser would need a credential; that is
deliberately out of scope for now.

!!! warning "The UI has write access"
    Anyone who can reach the NATS WebSocket can invoke agents. `oam ui`
    binds to localhost by default; prefer an SSH tunnel over `--host 0.0.0.0`
    for remote access.

## In a source checkout

The working tree has no compiled assets (`oam ui` will say so and exit).
Run the Vite dev server instead — it serves the app and `/config.json`
directly:

```bash
cd ui/ && pnpm install && pnpm dev
```
