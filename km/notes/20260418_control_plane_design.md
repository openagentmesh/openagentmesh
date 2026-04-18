# Control Plane: Agent and Channel Scoping

**Related:** ADR-0035, ADR-0033 (CLI surface)

## The Problem

A running mesh is flat: every agent sees every other agent, every channel is open. This works for small local meshes but breaks down when:

- Multiple teams share a mesh and shouldn't see each other's agents
- An agent needs to be taken offline for maintenance without killing the process
- A misbehaving publisher is flooding a channel and you need an instant kill switch
- An orchestrator should only route to a curated subset of agents

The control plane is the operator's tool for shaping what's visible and reachable at runtime.

## Core Concepts

### Agent States

Agents gain a lifecycle beyond "registered" and "gone":

```
active <-> paused <-> disabled
  |
  v
draining -> disabled
```

| State | In catalog | Invocable | Receives events | Use case |
|-------|-----------|-----------|-----------------|----------|
| `active` | yes | yes | yes | Normal operation |
| `paused` | yes (marked) | no (503) | no | Temporary maintenance, debugging |
| `disabled` | no | no | no | Decommissioned but process alive |
| `draining` | no | in-flight only | no | Graceful shutdown, rolling deploy |

"Paused" is the key state: the agent is still visible in discovery (so callers know it exists) but returns an error on invocation. Callers can decide to wait or pick an alternative.

### Channel Gates

Channels can be opened or closed independently of the agents that use them:

| Gate state | Publishers | Subscribers |
|------------|-----------|-------------|
| `open` | emit normally | receive normally |
| `closed` | emit silently dropped (or error, configurable) | stop receiving |

Gate state stored in a `mesh-control` KV bucket. SDK checks the gate before publishing; NATS subscription is paused (not removed) when a channel is closed.

### Scopes

A scope is a named partition of the catalog. Agents register into one or more scopes. Discovery queries can be scoped:

```python
# Register with scope
@mesh.agent(AgentSpec(
    name="translator",
    description="...",
    scopes=["nlp", "production"],
))

# Discover within scope
entries = await mesh.catalog(scope="nlp")
```

Scopes are additive tags, not hierarchical namespaces. An agent in scope "nlp" is also visible to unscoped queries (unless the mesh is configured as scope-required).

## CLI Surface

All control plane commands live under `oam control`. They follow the same conventions as the existing CLI (ADR-0033): human-readable by default, `--json` for machine output, mesh target resolved via `--url` / `OAM_URL` / `.oam-url`.

### Agent lifecycle

```bash
# List agents with their current state
oam control agents [--json]
NAME         STATE    SCOPES          SINCE
translator   active   nlp,production  2m ago
summarizer   paused   nlp             45s ago
ticker       active   market          10m ago

# Pause an agent (stops invocations, stays in catalog)
oam control pause <agent-name>
oam control pause translator
# translator: active -> paused

# Resume a paused agent
oam control resume <agent-name>
oam control resume translator
# translator: paused -> active

# Disable an agent (remove from catalog, reject all traffic)
oam control disable <agent-name>
oam control disable translator
# translator: active -> disabled

# Enable a disabled agent (re-register in catalog)
oam control enable <agent-name>
oam control enable translator
# translator: disabled -> active

# Drain an agent (stop new traffic, wait for in-flight to complete)
oam control drain <agent-name> [--timeout 30s]
oam control drain translator --timeout 10s
# translator: active -> draining -> disabled (after in-flight complete or timeout)
```

### Channel gates

```bash
# List channels and their gate state
oam control channels [--json]
CHANNEL          STATE   PUBLISHERS  SUBSCRIBERS
agent.translator open    1           3
health.>         open    5           1
market.ticks     closed  1           0

# Close a channel (stop message flow)
oam control close <channel>
oam control close market.ticks
# market.ticks: open -> closed

# Open a channel
oam control open <channel>
oam control open market.ticks
# market.ticks: closed -> open
```

### Scoping

```bash
# List scopes and their member counts
oam control scopes [--json]
SCOPE       AGENTS
nlp         2
production  1
market      1

# Show agents in a specific scope
oam control scope <name> [--json]
oam control scope nlp
NAME         STATE    DESCRIPTION
translator   active   Translate text between languages
summarizer   paused   Summarize text into N bullet points

# Add/remove an agent from a scope at runtime
oam control tag <agent-name> <scope>
oam control untag <agent-name> <scope>
oam control tag translator experimental
oam control untag translator production
```

### Bulk operations

```bash
# Pause all agents in a scope
oam control pause --scope nlp

# Drain all agents (mesh-wide maintenance)
oam control drain --all --timeout 60s

# Close all channels matching a pattern
oam control close 'market.*'
```

## SDK Surface

The SDK exposes the control plane for programmatic access, primarily for orchestrators and admin tools:

```python
# Read agent states
agents = await mesh.control.agents()
# [ControlEntry(name="translator", state="active", scopes=["nlp"]), ...]

# State transitions
await mesh.control.pause("translator")
await mesh.control.resume("translator")
await mesh.control.disable("translator")
await mesh.control.drain("translator", timeout=30)

# Channel gates
await mesh.control.close_channel("market.ticks")
await mesh.control.open_channel("market.ticks")
channels = await mesh.control.channels()

# Scoping
await mesh.control.tag("translator", "experimental")
await mesh.control.untag("translator", "production")
```

## Storage

Control plane state lives in a new KV bucket: `mesh-control`.

| Key pattern | Value | Purpose |
|-------------|-------|---------|
| `agent.<name>.state` | `active\|paused\|disabled\|draining` | Agent lifecycle state |
| `agent.<name>.scopes` | JSON array of scope strings | Scope membership |
| `channel.<pattern>.gate` | `open\|closed` | Channel gate state |

The catalog (`mesh-catalog`) continues to reflect the "logical" state: disabled agents are removed from the catalog; paused agents remain but with a `state: paused` field. The control bucket is the source of truth; the catalog is a derived view.

## Interaction with NATS Auth

NATS has its own permission system (accounts, users, subject permissions). The control plane operates at the application layer, above NATS auth:

- NATS auth: "can this connection publish to this subject?" (transport-level)
- OAM control plane: "should this agent be reachable right now?" (application-level)

They're complementary. For multi-tenant deployments, NATS accounts provide hard isolation. The OAM control plane provides soft, dynamic, operator-managed scoping within an account.

## Open Design Questions

1. **Error behavior for paused agents.** Should callers get a specific error code (e.g., `AgentPaused`) or a generic `AgentUnavailable`? A specific error lets callers implement retry-after logic.

2. **Channel close semantics.** Should closed channels silently drop messages or return an error to publishers? Silent drop is simpler but masks bugs; errors are noisier but honest.

3. **Scope enforcement level.** Three options:
   - Advisory: scopes filter `catalog()` results but don't prevent direct `call()` if you know the name
   - Enforced: `call()` to an out-of-scope agent fails
   - Configurable: mesh-level setting

4. **Control plane access control.** Who can pause/disable agents? Initially, anyone with CLI access. Later, tie into NATS auth or a separate admin role.

5. **Event notifications.** Should state transitions emit events on a control channel (`control.agent.translator.paused`)? Useful for dashboards and audit logs.

6. **Persistence across restarts.** Should control plane state survive a mesh restart? If stored in JetStream KV, it does. But should a "paused" agent auto-resume on mesh restart, or stay paused?

## Phasing

This is post-Phase 1 work. The foundation to lay now (if any):

- Reserve the `mesh-control` bucket name in the JetStream spec
- Ensure the catalog entry model has room for a `state` field
- Keep the `oam control` namespace free in the CLI router

The full implementation is Phase 2 or later.
