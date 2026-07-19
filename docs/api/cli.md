# CLI

`oam` is the command-line interface for inspecting and driving an OpenAgentMesh
deployment. It is primarily useful for local development, prototyping, and for
coding agents that need to interact with the mesh from a shell.

The binary is installed alongside the Python SDK.

## Connecting to a mesh

Every `oam` command needs to know which mesh to talk to. The URL is resolved in
this order:

1. `--url` flag on the command
2. `OAM_URL` environment variable
3. `.oam-url` file, looked up from the current directory walking up to the
   filesystem root
4. Default: `nats://localhost:4222`

`oam mesh up` writes `.oam-url` to the current directory automatically. To
point at a different mesh, use `oam mesh connect <url>`; add
`--creds <file>` for a secured mesh (the file then also supplies credentials
to `oam` commands and SDK processes run from that directory).

## `oam mesh`

### `oam mesh up`

Start a local NATS server with JetStream enabled and pre-create the required
KV buckets.

```bash
oam mesh up
```

```text
NATS listening on nats://127.0.0.1:4222
WebSocket listener on ws://127.0.0.1:4223 (browser clients, `oam ui`)
KV buckets ready: mesh-catalog, mesh-registry, mesh-context
Health monitor running (pid 12345)
Wrote .oam-url
```

The server runs detached by default. Use `--foreground` to block on the
current terminal, or `--port <n>` to bind a different port. A
[health monitor](../concepts/liveness.md) starts alongside the server so
crashed agents leave the catalog immediately and death notices fire.

### `oam mesh down`

Stop the mesh (and its health monitor) started by `oam mesh up`. This only
affects meshes managed via the PID file; embedded meshes (from `oam demo` or
`AgentMesh.local()`) are stopped with Ctrl+C in their own terminal.

```bash
oam mesh down
```

### `oam mesh monitor`

Run the [health monitor](../concepts/liveness.md) in the foreground against
any mesh. `oam mesh up` starts one for you; use this on secured meshes,
where advisories need a system-account credential and cleanup needs a
worker credential:

```bash
oam mesh monitor --url nats://mesh:4222 \
    --sys-creds monitor-sys.creds --creds worker.creds
```

### `oam mesh connect`

Point subsequent `oam` commands in this directory at an existing mesh by
writing `.oam-url`. Assumes the mesh is open (authentication is not yet
supported).

```bash
oam mesh connect nats://mesh.example.com:4222
```

### `oam mesh catalog`

List the agents currently registered in the catalog. Wraps
[`mesh.catalog()`](agentmesh.md#catalog).

```bash
oam mesh catalog
oam mesh catalog --channel nlp
oam mesh catalog --json
```

### `oam mesh listen`

Subscribe to a NATS subject (or wildcard) and print incoming messages as they
arrive. Useful for tapping health events, agent I/O, or any other mesh-level
channel.

```bash
oam mesh listen 'agent.translator.*'
oam mesh listen 'health.>'
```

Press Ctrl-C to stop. Pass `--json` to emit one JSON object per line
(`{"subject": ..., "data": ...}`).

## `oam agent`

### `oam agent call`

Invoke an agent and print its response. The payload is taken from the
positional argument, or from stdin if the argument is omitted.

```bash
oam agent call translator '{"text": "ciao", "target": "en"}'
echo '{"text": "ciao", "target": "en"}' | oam agent call translator
```

### `oam agent stream`

Same as `call`, but for streaming agents. Each chunk is printed as it arrives.

```bash
oam agent stream summarizer '{"text": "long document..."}'
```

### `oam agent subscribe`

Subscribe to a publisher agent's event stream. Each event is printed as it
arrives. Press Ctrl-C to stop.

```bash
oam agent subscribe price-feed
oam agent subscribe price-feed --json
oam agent subscribe price-feed --timeout 30
```

### `oam agent contract`

Fetch and display an agent's contract (A2A card plus OAM fields).

```bash
oam agent contract translator              # JSON (default)
oam agent contract translator --text       # compact text summary
```

!!! note "Agent health is not yet exposed"
    A user-facing `oam agent health` command is intentionally omitted from
    Phase 1. The underlying liveness signal (NATS disconnect advisories)
    gives a "definitely dead" read but not a positive "responding right
    now" confirmation, and synthesising the latter by invoking the user's
    handler with a sentinel payload is noisy and surprising. A dedicated
    framework-level ping subject, handled by the runtime rather than the
    user's code, will land in a future ADR.

## `oam auth`

Credential management for secured meshes (wraps
[nsc](https://github.com/nats-io/nsc); requires the `nsc` binary on PATH or
in `~/.agentmesh/bin/`). See [Securing the Mesh](../concepts/security.md).

### `oam auth init`

Bootstrap a credential tree in `.oam/`: an operator (with the system account
JetStream requires), a JetStream-enabled application account, and a
ready-to-run `server.conf` using a memory resolver.

```bash
oam auth init --name mymesh
nats-server -c .oam/server.conf
```

| Option | Default | Description |
|--------|---------|-------------|
| `--name` | `mesh` | Operator and account name |
| `--dir` | `.oam` | Where to put the credential store |

### `oam auth user add`

Create a user from a role template and write its `.creds` file (mode 0600).

```bash
oam auth user add risk-pipeline --role worker
```

| Option | Default | Description |
|--------|---------|-------------|
| `--role` | (required) | `worker`, `invoker`, or `observer` |
| `--dir` | `.oam` | Credential store directory |
| `--out` | `./<name>.creds` | Where to write the credentials |

Roles: `worker` hosts agents and uses the full SDK surface; `invoker` calls
agents and reads the catalog; `observer` is read-only (catalog, events,
errors, health).

### `oam auth user revoke`

Revoke a user and regenerate `server.conf`; reload or restart the server to
apply.

```bash
oam auth user revoke risk-pipeline
```

### `oam auth whoami`

Show the identity the CLI would connect with (resolved from `--creds`,
`OAM_CREDS`, or `.oam-url`), including the user name, public NKey, and
account.

```bash
oam auth whoami
```

## `oam observe`

Tail mesh log events and control per-agent log levels. See
[Observability](../concepts/observability.md).

### `oam observe logs`

Tail structured log events (Ctrl-C to stop).

```bash
oam observe logs                     # all agents
oam observe logs nlp.summarizer      # one agent
oam observe logs --level warn        # minimum level filter
```

### `oam observe config`

Show observability config: the mesh-wide default plus per-agent overrides,
or the effective config (and its source tier) for one agent.

```bash
oam observe config
oam observe config nlp.summarizer
oam observe config --json
```

### `oam observe set`

Set the log level for one agent or mesh-wide. Applies live — hosts pick up
the change via KV watch, no restart.

```bash
oam observe set nlp.summarizer --log-level debug
oam observe set --global --log-level warn
```

Levels: `debug`, `info`, `warn`, `error`, `off`.

## `oam ui`

Serve the [admin UI](../cookbook/admin-ui.md): agent registry, invocation
sandbox, and live event feed in the browser. The mesh must already be
running; the browser connects to the mesh's WebSocket listener directly.

```bash
oam ui                               # serve on http://127.0.0.1:4224
oam ui --port 8080                   # custom port (falls back if taken)
oam ui --nats-ws-url ws://host:4223  # WebSocket URL handed to the browser
oam ui --check                       # print resolved config and exit
```

```text
Admin UI running at http://127.0.0.1:4224
Browser will connect to ws://localhost:4223 (NATS WebSocket)
```

The mesh URL resolves like every other command (`.oam-url` → `OAM_URL` →
default); the browser's WebSocket URL defaults to the same host on mesh
port + 1, overridable with `--nats-ws-url` or `OAM_NATS_WS_URL`. Binds to
localhost by default — the UI carries mesh write access, so prefer an SSH
tunnel over `--host 0.0.0.0` (or `OAM_UI_HOST`) for remote use.

Release wheels bundle the compiled UI assets; in a source checkout run the
Vite dev server instead (`cd ui/ && pnpm dev`).

## Output conventions

All commands that produce structured output default to a human-readable format
and accept `--json` for machine-parseable output. Errors are written to stderr
and cause a non-zero exit code; successful output goes to stdout so it can be
piped into other tools.
