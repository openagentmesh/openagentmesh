# Enterprise Agent Runtime (working title)

Status: brainstorm. Not an ADR. Not a commitment.

## What this is

A separate project built on top of OpenAgentMesh. OAM provides the roads (transport, discovery, contracts); this layer provides the cars (runtime, governance, patterns) and the ecosystem (plugins, adapters, deploy artifacts).

Inspired by NanoClaw v2 (`km/notes/`-style reference: https://github.com/qwibitai/nanoclaw), but NanoClaw is a single-node personal assistant that conflates orchestration and delivery in one Node process. The intent here is the multi-agent, distributed, governed shape that NanoClaw points at but does not deliver.

## What this is not

- Not OAM. OAM stays a clean protocol + SDK.
- Not a LangGraph competitor. LangGraph is a graph-authoring library for in-process workflows. This layer sits beneath it. LangGraph is a potential consumer.
- Not a framework first. Framework patterns come after the runtime and governance layers exist.
- Not a NanoClaw clone. NanoClaw is single-tenant, single-node, channel-in-channel-out. This is multi-tenant, distributed, agent-to-agent.

## Target users

Enterprise architects and devops/platform teams. Architects pick, devops operate. First conversation partner needs to be picked: probably devops, since they ship faster and architects follow validated peers.

Pitch (working): "Kubernetes did not make apps; it made apps operable at scale. We do that for agents."

## The gap

| Need | LangGraph (today) | This layer |
|---|---|---|
| Lifecycle (spawn, heal, retire) | none | OAM-native + K8s operator |
| Checkpointing + resume | in-process | distributed (JetStream + KV) |
| Cross-agent shared state | n/a | scoped state buckets, isolation rules |
| HITL | sync interrupt | async, multi-channel, auditable approvals |
| Observability | LangSmith (hosted) | OTel through mesh, cost attribution, contract diffs |
| Governance | none | RBAC on subjects, policy engine, audit log |
| Deploy | LangGraph Cloud | K8s artifacts, sidecar patterns, on-prem story |
| Multi-tenant | no | accounts, isolation, quotas |
| Secrets | env vars | credential broker, scoped, approval-gated |
| Replay / time travel | yes (in-process) | subject-level replay from JetStream |

LangGraph has the in-process story. Nobody has the distributed-enterprise story at this maturity. That is the white space.

## Layered stack

```
6. Platform UX        CLI, dashboard, deploy artifacts
5. Ecosystem          channel adapters, tool libs, provider bridges
4. Patterns/Framework graph+mesh workflows, HITL patterns, pipelines
3. Governance         auth, RBAC, approvals, audit, policy engine
2. Runtime            lifecycle, checkpointing, retries, replay, OTel
1. OAM                transport, discovery, contracts
```

Each layer = candidate sub-project or plugin boundary. Only layers 1 and 2 need to be tightly coupled.

## What to steal from NanoClaw

- Agents as persistent workers with identity, memory, skills (not call-response tools).
- Channel adapters as the human UX surface; multi-channel is table stakes for enterprise.
- Approval primitive as a cross-cutting concern (the OneCLI dance).
- Skills/extensions installed from sibling branches (idempotent install pattern).
- Isolation model (shared / scoped / separate) as a deploy-time choice.

## What to NOT carry over from NanoClaw

- Two-DB polling as transport. OAM already wins here.
- Single Node process owning lifecycle + delivery + sweep + approvals. Split these.
- Heartbeat as file touch. NATS client presence is enough.
- Per-session container as the only execution model. Stateless handlers + queue groups are the OAM-native shape; sessions are a layer above.

## Sharp design tensions

### Graph vs mesh

LangGraph forces upfront edge declaration. OAM is dynamic discovery. Three options:

1. **Graph-first**: declare workflows, runtime executes via subjects. Familiar, loses dynamism.
2. **Mesh-first**: agents autonomous, coordinate via contracts. Flexible, no visual graph.
3. **Hybrid**: graphs for deterministic pipelines, mesh for swarms. Honest about reality, hardest to get clean.

Hybrid probably right. Cost is API surface area.

### Polyglot vs Python-only

Enterprise agent code is Python-heavy today, TypeScript rising. OAM is protocol-first so polyglot is feasible. Decide early; affects SDK API and contract serialization.

### Hosted vs self-hosted

LangGraph has Cloud. Enterprise OSS that cannot be hosted loses half the market. Decide if a hosted offering is on the roadmap. If yes, multi-tenancy must be in the substrate from day one.

### Maximum flexibility vs opinionated defaults

Tension. Enterprise wants opinionated defaults. Pick a few sharp opinions ("all agents emit OTel", "all credential access goes through broker", "all approvals go to the audit log") and make them hard to bypass. Flexibility lives elsewhere.

## MVP scoping

Ruthless scope. One person cannot build all six layers in any reasonable time.

- **v0.1**: Runtime SDK on top of OAM (Python). Lifecycle, checkpointing to JetStream/KV, OTel propagation. That is it.
- **v0.2**: Governance primitives. Policy engine (subject ACLs), approval agent, audit log. Credential broker as a separate agent (NanoClaw OneCLI-shaped).
- **v0.3**: One reference workflow pattern (plan-execute-review with HITL) + one reference deploy (Helm chart or K8s operator).
- **v0.4**: Two channel adapters (Slack + web) + minimal dashboard.

Everything else (more workflows, more channels, more providers, more tools) = community plugins or later releases.

## Competitive positioning

- **LangGraph / CrewAI / AutoGen**: in-process. Beneath them, not against them.
- **Magentic-One (per `km/notes/20260423_competitors.md` reading)**: HTTP-based, less capable transport. Microsoft has distribution; differentiate on (a) open protocol, no lock-in, (b) real mesh, not HTTP fan-out, (c) contracts as first-class, not ad-hoc JSON.
- **Temporal AI / dbos**: workflow engines, deterministic, agents as workers. Different shape. Could integrate (Temporal as a workflow engine that calls agents on the mesh).
- **Anthropic Managed Agents / E2B / Modal**: hosted, opinionated, vendor-tied. Open + protocol-first is the OSS counter.

## Open questions (resolve before scoping further)

1. Devops or architect as first user? Affects what ships in v0.1.
2. Python-only or polyglot from day one?
3. Hosted on the roadmap or pure OSS?
4. Graph-first, mesh-first, or hybrid?
5. Does this share a repo with OAM, sit in a sibling repo, or live in a new org?
6. Naming. Working title aside, the project needs a name that signals "agent ops platform" without colliding with AgentOps the company.
7. Dependency direction: does this layer assume a specific OAM version, or pin to protocol revisions?
8. What is the smallest end-to-end demo that an architect would find credible? (e.g. "two agents on different nodes, one calls the other under a policy gate, with full OTel trace and an audit log entry") This becomes the v0.1 acceptance criteria.

## Pre-commitments (so future-me does not drift)

- Phase 1 of OAM ships first. This note does not get acted on until OAM is at least at MVP.
- ADR-0038 (authn) must be implemented before governance layer (v0.2) is even designed. Identity is load-bearing.
- No code in this repo for this project. When work starts, it is a separate repo.
- This note is a brainstorm. Decisions belong in ADRs, in the new project.
