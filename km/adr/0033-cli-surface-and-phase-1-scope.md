# ADR-0033: CLI surface and Phase 1 scope

## Status

spec

## Context

OAM needs a CLI for three primary audiences: (1) coding agents that drive the mesh programmatically from a shell, (2) developers prototyping locally, and (3) operators inspecting a running mesh. Two earlier drafts are in conflict: `pyproject.toml` declares a `mesh` entry point, `docs/api/cli.md` documents `mesh up` / `mesh status`, and the newer design notes in `km/notes/20260416_CLI_design.md` specify `oam` as the binary with a richer command tree.

The notes are the most recent and reflect the intended direction. Several open questions in the notes remain unresolved. This ADR resolves them and fixes the Phase 1 scope.

## Decision

### Binary name

The CLI binary is `oam`. The `mesh = openagentmesh.cli:app` entry in `pyproject.toml` is superseded by `oam = openagentmesh.cli:app`. The previous `docs/api/cli.md` content is superseded by this ADR and will be rewritten when the CLI is documented.

### Design rules

- **Output:** human-readable by default; every command that produces structured output supports `--json`.
- **Mesh target resolution,** in order of precedence:
  1. `--url` flag
  2. `OAM_URL` environment variable
  3. `.oam-url` file, looked up from the current directory walking up to the filesystem root
  4. Default `nats://localhost:4222`
- **Auth:** assumed open (no credentials). Auth is deferred to a future ADR.
- **Backend:** NATS-only. A `MeshBackend` plugin protocol is deferred until a concrete second backend is needed.
- **Invocation payload:** positional JSON string argument, or piped via stdin if the argument is omitted. No `--interactive` prompt mode in Phase 1.
- **Channel listening:** scoped under `oam mesh listen <channel>`, supporting NATS wildcards (`*`, `>`). Channels cover agent I/O, health, and any other mesh-level subjects.

### Phase 1 MVP command surface

```
oam mesh up                         # start local NATS + JetStream + KV buckets; write .oam-url
oam mesh down                       # stop the local mesh started by `up`
oam mesh connect <url>              # persist <url> to .oam-url in cwd (open mesh, no auth)
oam mesh catalog [--json]           # list registered agents (wraps mesh.catalog())
oam mesh listen <channel> [--json]  # tap a channel or wildcard, stream messages to stdout
oam agent call <name> [payload]     # invoke; payload is JSON arg or stdin
oam agent stream <name> [payload]   # invoke streaming; chunks to stdout
oam agent inspect <name> [--json]   # dump the contract (A2A card + x-agentmesh)
oam agent health <name> [--json]    # two-axis health: registered + responsive
```

### Health semantics

`oam agent health <name>` reports two independent axes:

- **registered:** whether the agent has an entry in the catalog KV bucket.
- **responsive:** lightweight ping via a short-timeout invocation on the agent's subject.

This avoids inventing a new health primitive. `registered` uses the existing catalog; `responsive` uses the existing invocation path. Disconnect advisories (ADR-0016) remain the internal liveness signal; `health` is a user-facing summary over observable state.

### `oam mesh connect` semantics

`connect` is a local operation: it writes `<url>` to `.oam-url` in the current working directory. Subsequent `oam` commands from that directory resolve to that mesh. `oam mesh up` writes `.oam-url` automatically with the URL of the instance it started. No authentication is performed; the mesh is assumed open. Auth belongs to a separate ADR once the authz/n framework is defined.

### Deferred to future ADRs

- `oam kv` subcommands (ls/get/put/rm, bucket management) — trivial wrappers once the core KV surface stabilizes.
- `oam obj` subcommands (object store).
- Adapter plugin system for non-NATS backends.
- Credentials and auth for remote meshes.

## Code samples (DX contract)

Starting a local mesh and inspecting it:

```bash
$ oam mesh up
NATS listening on nats://localhost:4222
KV buckets ready: mesh-catalog, mesh-registry
Wrote .oam-url

$ oam mesh catalog
NAME        TYPE       STREAMING  DESCRIPTION
summarizer  agent      yes        Summarize text into N bullet points
translator  tool       no         Translate text between languages
ticker      publisher  -          Emit market ticks every second
```

Invoking agents:

```bash
$ oam agent call translator '{"text": "ciao", "target": "en"}'
{"translated": "hello"}

$ echo '{"text": "ciao", "target": "en"}' | oam agent call translator
{"translated": "hello"}

$ oam agent stream summarizer '{"text": "long document..."}'
First bullet
Second bullet
Third bullet
```

Inspecting and probing:

```bash
$ oam agent inspect translator --json
{
  "name": "translator",
  "description": "...",
  "capabilities": {"streaming": false},
  "x-agentmesh": {"type": "tool"},
  ...
}

$ oam agent health translator
registered: yes
responsive: yes (8 ms)
```

Tapping the mesh:

```bash
$ oam mesh listen 'agent.translator.*'
[agent.translator.in ] {"text": "ciao", "target": "en"}
[agent.translator.out] {"translated": "hello"}

$ oam mesh listen 'health.>'
[health.summarizer] alive
[health.translator] alive
```

Connecting to a remote mesh (open):

```bash
$ oam mesh connect nats://mesh.example.com:4222
Wrote .oam-url

$ oam mesh catalog
# now queries the remote mesh
```

## Consequences

- `pyproject.toml` entry point renamed: `mesh` -> `oam`. Anyone who installed an earlier dev version will lose the `mesh` command.
- `docs/api/cli.md` is rewritten to match this ADR once the CLI reaches `documented`.
- Adds `.oam-url` as a conventional per-project file. Add to `.gitignore` template examples in the quickstart.
- Typer is already a dependency; `rich` is added for tables and human output.
- `oam mesh listen` makes NATS wildcard semantics visible to CLI users. This is acceptable: the CLI is an operator-facing tool and NATS is the only backend in Phase 1.
- `oam agent health` defines a stable two-axis contract that later implementations (including non-NATS) can preserve without redesign.

## Open items tracked for later ADRs

- ADR (pending): `oam kv` / `oam obj` surface.
- ADR (pending): Auth model for `oam mesh connect` to non-open meshes.
- ADR (pending): Adapter/backend plugin protocol once a second backend is proposed.
