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
point at a different mesh, use `oam mesh connect <url>`.

## `oam mesh`

### `oam mesh up`

Start a local NATS server with JetStream enabled and pre-create the required
KV buckets.

```bash
oam mesh up
```

```text
NATS listening on nats://127.0.0.1:4222
KV buckets ready: mesh-catalog, mesh-registry, mesh-context
Wrote .oam-url
```

The server runs detached by default. Use `--foreground` to block on the
current terminal, or `--port <n>` to bind a different port.

### `oam mesh down`

Stop the mesh started by `oam mesh up`. This only affects meshes managed via the
PID file; embedded meshes (from `oam demo` or `AgentMesh.local()`) are
stopped with Ctrl+C in their own terminal.

```bash
oam mesh down
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

## Output conventions

All commands that produce structured output default to a human-readable format
and accept `--json` for machine-parseable output. Errors are written to stderr
and cause a non-zero exit code; successful output goes to stdout so it can be
piped into other tools.
