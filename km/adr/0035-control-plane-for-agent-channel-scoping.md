# ADR-0035: Control plane for agent and channel scoping

- **Type:** architecture
- **Date:** 2026-04-18
- **Status:** discussion
- **Source:** conversation (future development idea)

## Context

In a service mesh like Istio or Linkerd, the control plane governs which services are reachable, which routes are active, and what policies apply at runtime. OpenAgentMesh currently has no equivalent: once agents register on the mesh, they are universally discoverable and invocable by any other agent. There is no mechanism to limit visibility, disable agents, or gate access to channels without stopping the agent process itself.

As meshes grow beyond a handful of agents, operators need the ability to:

1. **Scope agent visibility.** An orchestrator agent should only see the agents relevant to its workflow, not every agent on the mesh.
2. **Disable agents at runtime.** Take an agent offline (stop it from receiving invocations) without killing its process, for maintenance, canary rollouts, or incident response.
3. **Gate channels.** Enable or disable pub/sub channels so that event flows can be controlled without redeploying publishers or subscribers.
4. **Apply policies dynamically.** Rate limits, access control, or routing rules that change without restarting agents.

This is analogous to Istio's traffic management (VirtualService, DestinationRule) but scoped to the agent mesh domain: catalog filtering, invocation routing, and channel lifecycle.

## Design Space

Several approaches are worth exploring:

### Catalog-level filtering

The catalog (`mesh.catalog()`) is already the discovery entry point. A scoping layer could filter catalog results per-caller, so agents only see what they're allowed to see. This could be implemented as:

- **Scopes on the mesh instance.** `AgentMesh(scope="workflow-alpha")` only returns catalog entries tagged with that scope.
- **Per-agent ACLs in the catalog.** Each catalog entry includes a `visibility` field listing which agents or groups can discover it.

### Agent state machine

Add lifecycle states beyond "registered" and "gone":

| State | Discoverable | Invocable |
|-------|-------------|-----------|
| `active` | yes | yes |
| `paused` | yes (marked as paused) | no (returns error) |
| `disabled` | no | no |
| `draining` | no (to new callers) | yes (in-flight only) |

Transitions triggered via CLI (`oam pause agent-name`), API (`mesh.control.pause("agent-name")`), or a control plane UI.

### Channel gates

Channels (pub/sub subjects) could have an enabled/disabled toggle stored in a KV bucket. Publishers check the gate before emitting; subscribers stop receiving when the channel is gated. This gives operators a kill switch for event flows without touching agent code.

### Policy engine

A more ambitious direction: a lightweight policy layer (OPA-style or simpler) where rules like "agent X can only call agents tagged `tools`" or "channel `audit.*` is read-only for non-admin agents" are evaluated at invocation time. This is powerful but adds significant complexity.

## Open Questions

- Is this a Phase 2 concern, or should the foundation (agent states, catalog scoping) be designed into Phase 1's data model now to avoid migration pain later?
- Should scoping be enforced at the SDK level (catalog filtering), the NATS level (subject permissions), or both?
- How does this interact with NATS's built-in auth and permissions? Can we lean on NATS account isolation instead of building a custom control plane?
- Is a CLI-driven control plane sufficient, or does this eventually need a UI (admin dashboard)?
- Should "paused" agents still respond to health checks and liveness probes?
- How does scoping interact with the A2A federation boundary? Should federated agents respect local scoping rules?
