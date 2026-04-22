# ADR-0035: Control plane for agent and channel scoping

- **Type:** architecture
- **Date:** 2026-04-18
- **Status:** discussion
- **Related:** ADR-0037 (OAM scope), ADR-0038 (NATS authentication)
- **Source:** conversation (future development idea), authn/z shaping session (2026-04-22)

## Context

In a service mesh like Istio or Linkerd, the control plane governs which services are reachable, which routes are active, and what policies apply at runtime. OpenAgentMesh currently has no equivalent: once agents register on the mesh, they are universally discoverable and invocable by any other agent. There is no mechanism to limit visibility, disable agents, or gate access to channels without stopping the agent process itself.

As meshes grow beyond a handful of agents, operators need the ability to:

1. **Scope agent visibility.** An orchestrator agent should only see the agents relevant to its workflow, not every agent on the mesh.
2. **Disable agents at runtime.** Take an agent offline (stop it from receiving invocations) without killing its process, for maintenance, canary rollouts, or incident response.
3. **Gate channels.** Enable or disable pub/sub channels so that event flows can be controlled without redeploying publishers or subscribers.
4. **Apply policies dynamically.** Rate limits, access control, or routing rules that change without restarting agents.

This is analogous to Istio's traffic management (VirtualService, DestinationRule) but scoped to the agent mesh domain: catalog filtering, invocation routing, and channel lifecycle.

## Two-tier security model

The authn/z shaping session (ADR-0037, ADR-0038) surfaced a clear split between open-source and enterprise trust models. The control plane sits at the center of this split.

### OSS tier: network perimeter + cooperative scope

The open-source security model is network-level: the NATS server sits behind a VPN, firewall, or private subnet. If you can't reach the port, you can't connect. This is the same model most open-source infrastructure uses (Redis, Elasticsearch, Kafka out of the box).

Inside that perimeter, ADR-0037's cooperative scope shapes the interaction topology for honest agents. Scope is not a security boundary; the network perimeter is. This is valid and sufficient for single-team, single-org deployments where all agents are your own code.

| Component | OSS role |
|-----------|----------|
| Network perimeter | Trust boundary (who can connect) |
| ADR-0037 scope | Topology shaping (who sees/calls whom) |
| ADR-0038 auth | Optional hardening (password or NKey on the NATS port) |
| Control plane | Operational tooling: pause, drain, inspect |

### Enterprise tier: per-agent enforcement + credential broker

When the mesh is opened to agents you don't fully control (third-party integrations, multi-team shared meshes, hosted platforms), network-level gating is no longer sufficient. The control plane becomes the centralized enforcement layer:

- **Credential broker.** The control plane issues per-agent NATS users with tightly scoped subject permissions. Each agent (or agent group) gets its own NATS connection with only the subjects it needs. This is the per-agent credentials model that ADR-0037/0038 rejected for the SDK layer (credential explosion at the developer level), but it becomes manageable when a broker automates issuance, rotation, and revocation.
- **Central policy store.** Per-agent policy (who can call whom, which channels are active, visibility rules) lives in the control plane, not in agent code. The control plane projects policy into NATS permissions and/or OAM scope overrides.
- **Operator UI.** Dashboard for the policy table: who can call whom, which channels are active, credential lifecycle, effective permissions per agent. The operator interface that ADR-0035's CLI commands are the programmatic equivalent of.
- **Runtime enforcement.** Pause, disable, drain, and revoke translate to credential revocation or NATS permission updates pushed by the broker. Server-side enforcement, not cooperative.

| Component | Enterprise role |
|-----------|----------------|
| Network perimeter | Still present, but not the only boundary |
| ADR-0037 scope | Still useful for intra-process topology (multiple agents per process) |
| ADR-0038 auth | Foundation: NKey + JWT credentials issued by the broker |
| Control plane | Credential broker + policy engine + operator UI |

### Monetization boundary

The OSS SDK ships cooperative scope (ADR-0037) and optional NATS auth passthrough (ADR-0038). These are genuinely useful for single-team development. The enterprise tier adds server-side enforcement, centralized policy management, and the operator UI. No feature crippling of the OSS version; the tiers serve different trust models for different deployment contexts.

## Design Space

Several approaches are worth exploring for the control plane's operational capabilities:

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

Transitions triggered via CLI (`oam pause agent-name`), API (`mesh.control.pause("agent-name")`), or the operator UI.

### Channel gates

Channels (pub/sub subjects) could have an enabled/disabled toggle stored in a KV bucket. Publishers check the gate before emitting; subscribers stop receiving when the channel is gated. This gives operators a kill switch for event flows without touching agent code.

### Policy engine

A more ambitious direction: a lightweight policy layer (OPA-style or simpler) where rules like "agent X can only call agents tagged `tools`" or "channel `audit.*` is read-only for non-admin agents" are evaluated at invocation time. This is powerful but adds significant complexity. In the enterprise tier, this could be the central policy store that the credential broker reads from.

## Relationship to ADR-0037 and ADR-0038

ADR-0037 supplies the **mechanism** that the control plane manipulates at the SDK layer:

- Runtime scope changes push new contracts (for `can_receive_from`) or update a live mesh instance's declared scope (for `can_call` / `can_see`).
- `paused` / `disabled` states can be implemented as forced `can_receive_from: []` at the control-plane layer.
- Channel gates become control-plane-owned scope overrides injected into callers' resolution path.

ADR-0038 supplies the **enforcement primitives** that the enterprise control plane brokers:

- Per-agent NATS users with scoped subject permissions.
- Credential rotation and revocation via account JWT re-push.
- Role templates (`worker`/`invoker`/`observer`) as the coarse starting point that the broker refines per-agent.

ADR-0037's open question "should scoping be enforced at the SDK level, the NATS level, or both?" is answered: **both, at different granularities, for different deployment tiers.** The OSS tier relies on SDK-level scope (cooperative) backed by network-level access control. The enterprise tier adds NATS-level enforcement (server-side) managed by the credential broker.

## Open Questions

- Is the agent state machine (active/paused/disabled/draining) an OSS feature or enterprise-only? Leaning OSS: it's operational tooling, not a security boundary.
- Should the enterprise credential broker be a standalone service or embedded in the NATS server (via auth callout)?
- How does the broker handle the transition window when revoking credentials for a running agent? Graceful drain vs. hard disconnect.
- What is the minimum viable policy model? Per-agent allowlists may be sufficient before introducing a full policy engine.
- How does this interact with multi-account tenancy (deferred in ADR-0038)? Accounts may replace or complement the broker for hard tenant isolation.
- Should "paused" agents still respond to health checks and liveness probes?
- How does scoping interact with the A2A federation boundary? Should federated agents respect local scoping rules?
