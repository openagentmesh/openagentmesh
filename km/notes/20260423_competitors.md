# Competitors and adjacent projects

Working notes on the agent-infrastructure landscape. Not exhaustive; updated as new entries surface. Purpose: clarify where OAM sits, sharpen positioning, spot threats.

## Positioning recap

OAM is a **protocol + SDK**: typed contracts, NATS transport, decentralized discovery. Deliberately narrow. Analogy: **service mesh for agents** (Istio/Linkerd, not Kubernetes).

What OAM is NOT:
- Not an LLM gateway (no multi-provider routing, no cost tracking).
- Not a prompt registry.
- Not an agent-memory store.
- Not a workflow orchestrator (composition lives in the handler body).
- Not a framework for *building* agents (no chains, no graphs, no tools abstraction).

The handler body is the developer's territory. OAM owns the wire, the contract, and discovery.

## Two-axis pitch

Competitors split cleanly by process model. OAM pitches differently against each.

**Against single-process frameworks (LangChain, CrewAI, LangGraph, AutoGen):** isolation.
- Single-process agents load all DB connections, API keys, and MCP clients into one runtime. Compromise of one tool path = full credential exposure.
- OAM agents run as independent processes with independent NATS identities. Per-agent subject permissions = capability-based access. Compromise of agent A bounds attacker to A's NATS perms (typed call surface to agent B), not raw access to B's DB or keys.
- These frameworks cannot match isolation without rewriting their core single-process model.

**Against multi-process alternatives (custom microservices, raw NATS, gRPC mesh, Temporal-for-AI):** simplicity.
- They already have isolation. Cannot out-isolate them.
- Win is DX: decorator + handler shape inference + typed contracts inferred for free, embedded NATS for local dev (`AgentMesh.local()`), `agentmesh up` for prod. No service registry, no protobuf toolchain, no Envoy config.

**Against MCP: orthogonal, not competing.**
- MCP isolates the *tool* process from the *agent* process. The agent still loads N MCP clients = holds N auth contexts. Compromise the agent, attacker reaches all N tools.
- OAM isolates *agents from each other*. Agent A calls agent B calls tool. A holds NATS perm to call B's subject only.
- Different granularity: MCP = tool isolation, OAM = agent isolation. Stack them, do not pick one.

**Honest caveat:** isolation alone is not the headline differentiator. Microservices have offered process isolation for 20 years. The OAM win is *isolation + typed contracts + dynamic discovery on a shared bus*, packaged with a decorator-grade DX. Lead with fabric/discovery; isolation is the security follow-on, not the opener.

## Landscape map

Three layers where "AI agent infrastructure" products cluster. OAM is layer 1; most competitors conflate 1 + 2 or 2 + 3.

| Layer | Concern | Examples |
|---|---|---|
| 1. Fabric | Transport, discovery, contracts, invocation | **OAM**, A2A (spec), MCP (tools only) |
| 2. Platform | LLM gateway, prompts, memory, cost, observability | MagiC, Portkey, LangSmith, Langfuse |
| 3. Framework | Agent construction (chains, graphs, state) | CrewAI, LangGraph, AutoGen, PydanticAI |

## Entries

### MagiC (kienbui1995/magic)

- **URL:** https://github.com/kienbui1995/magic
- **Stack:** Go core server, Python/Go/TS SDKs, HTTP REST dispatch.
- **Pitch:** "Kubernetes for AI agents." Bundles LLM gateway, prompt registry, agent memory, cost tracking, DAG workflows.
- **Layer:** 1 + 2 (fabric + platform, fused).
- **Overlap with OAM:** decorator worker registration, capability declaration, discovery, routing.
- **Key distinctions:**
  - Central HTTP control plane (Go server) vs OAM's decentralized NATS fabric.
  - Capability strings ("greeting", "content_writing") vs OAM's Pydantic-typed contracts (A2A superset, JSON Schema).
  - Server-side router picks worker (best_match, cheapest) vs NATS queue groups (native load balance, no orchestrator).
  - Bundles LLM ops (gateway, cost, memory) vs OAM's explicit punt to handler body.
- **Competitive read:** different philosophy. MagiC competes with CrewAI + Temporal-for-AI, not with OAM. Conceivable MagiC-style platform features run *as specialized agents* on top of an OAM fabric.
- **Risk to OAM:** MagiC's "batteries included" pitch is more immediately legible to buyers than "protocol + SDK." Buyers who want to ship fast pick MagiC; buyers who want to avoid lock-in and run polyglot pick OAM, but they have to be sold on that tradeoff.

### A2A (Agent-to-Agent Protocol, Google)

- **Layer:** 1 (fabric, spec only).
- **Overlap:** OAM's contract schema is a superset of A2A Agent Card. Intentional interop target.
- **Distinction:** A2A is cross-organization federation over HTTPS. OAM is intra-mesh over NATS. Complementary; federation gateway planned.

### MCP (Model Context Protocol, Anthropic)

- **Layer:** 1 (fabric), but scope is tools/resources, not agent-to-agent invocation.
- **Overlap:** minimal. MCP is "LLM ↔ tool"; OAM is "agent ↔ agent."
- **Distinction:** different consumer (LLM vs agent), different lifetime (request vs long-running), different transport (stdio/SSE vs NATS). Bridges are a compatibility feature, not convergence.

### CrewAI / LangGraph / AutoGen

- **Layer:** 3 (framework).
- **Overlap:** none at the protocol layer. These build single-process agent graphs.
- **Relationship:** an OAM agent's *handler body* could be a CrewAI crew or a LangGraph graph. OAM doesn't care. These are consumers, not competitors.

### Temporal, Celery, Ray Serve

- **Layer:** 2 (platform, generic).
- **Overlap:** worker pools, task dispatch.
- **Distinction:** generic compute, no AI-specific concerns, no typed agent contracts. MagiC positions against these; OAM does not.

## Positioning sharpening (TODO for docs)

Current OAM docs lead with "multi-agent SDK." Risk: buyers conflate with CrewAI/MagiC and bounce.

Proposed sharpening:
1. Lead with **"the wire, not the workflow."** OAM owns transport + contracts + discovery. The handler body is yours.
2. Explicit **anti-features list** in `docs/index.md` or concept overview: "OAM does not provide LLM routing, prompt management, agent memory, or workflow orchestration. Those are platform concerns; build them as agents on the mesh, or bring your own."
3. Side-by-side comparison page: OAM vs MCP, OAM vs A2A, OAM vs CrewAI, OAM vs MagiC. One short paragraph each, linking to this note for depth.

Open question: is the narrow positioning a feature or a go-to-market risk? Fabric-first is architecturally cleaner but harder to sell than a bundled platform. Revisit after first external users.
