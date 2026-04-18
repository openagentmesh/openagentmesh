# ADR-0036: Orchestration: declarative workflows and checkpointing

- **Type:** architecture
- **Date:** 2026-04-18
- **Status:** discussion
- **Source:** conversation (future development idea)

## Context

OpenAgentMesh today gives agents a way to find and call each other, but it has no opinion on how multi-step workflows are composed or how their state is managed. If an orchestrator agent coordinates a pipeline of five downstream agents and the process crashes halfway, there is no built-in way to resume from the last completed step. The workflow exists only in the caller's Python code and memory.

Two user-facing patterns show up repeatedly in multi-agent systems:

1. **Declarative workflows.** An operator or engineer describes a pipeline as data (YAML, JSON, visual editor) rather than code: "call agent A, feed its output into agent B, branch on a condition, run C and D in parallel, merge." This is the Airflow / Argo / n8n / Temporal-workflow-as-YAML mental model. Valuable because workflows become inspectable artifacts, versionable in git, editable by non-developers, and portable across teams.

2. **Checkpointed graph execution.** Each node transition in a workflow is persisted to durable storage, so the workflow can be paused, resumed, replayed, forked, or time-travelled. This is the LangGraph mental model (and, at a different altitude, Temporal's event sourcing). Valuable because it gives you crash recovery, human-in-the-loop pauses, A/B branching from a saved state, and step-by-step debugging as first-class features rather than ad-hoc logging.

These are often conflated but they are orthogonal axes. The composition surface (how the workflow is described) is independent of the execution model (how state is managed between steps). OAM needs to decide which, if either, it takes on as a first-class primitive, and which it leaves to user code or a downstream plugin (see the Mesh Plugins idea in `km/ideas.md`).

## Design Space

### Composition surface

**A. Programmatic only (status quo).** Orchestration is whatever Python the caller writes. `mesh.call()` and `mesh.stream()` are the primitives. The SDK has no opinion.

**B. Declarative YAML workflow.** A YAML document describes nodes (agent calls) and edges (data flow, conditions, branches). The SDK ships a runtime that reads the YAML and drives the execution. Example sketch:

```yaml
workflow: research-and-summarize
nodes:
  - id: research
    agent: researcher
    input: { query: "{{ input.query }}" }
  - id: critique
    agent: critic
    input: { draft: "{{ research.output }}" }
    depends_on: [research]
  - id: summarize
    agent: summarizer
    input: { text: "{{ critique.output }}" }
    depends_on: [critique]
output: "{{ summarize.output }}"
```

**C. Graph API in Python.** Nodes and edges declared programmatically (LangGraph-style), with the same runtime semantics as YAML but type-checked. The YAML is a serialization of this graph.

### Execution model

**X. Ephemeral.** Workflow state lives in the caller's process. Crash loses everything. Simplest, matches status quo.

**Y. Checkpointed.** Every node transition writes `{workflow_id, step, input, output, timestamp}` to `mesh-context` KV (or a dedicated `mesh-workflows` bucket). The runtime can resume from the last successful checkpoint. Gives:

- Crash recovery: resume after process death
- Human-in-the-loop: pause at a node, inject input, resume
- Replay: re-run from any checkpoint with modified inputs
- Forking: branch from a saved state to explore alternatives
- Observability: the checkpoint log is the audit trail

**Z. Event-sourced.** Every state change is an event on a JetStream stream, state is rebuilt by replaying events. This is Temporal's model. More powerful but heavier.

### Orthogonality

Composition and execution compose independently:

|            | Ephemeral (X)         | Checkpointed (Y)             | Event-sourced (Z)       |
|------------|-----------------------|-----------------------------|-------------------------|
| YAML (B)   | Simple pipeline tool  | YAML + LangGraph-like replay | Temporal-as-YAML        |
| Graph (C)  | In-process DAG        | LangGraph-equivalent         | Temporal-workflow-as-code |
| Code (A)   | Status quo            | Manual checkpointing         | Manual event sourcing   |

The most requested combination in the LangGraph ecosystem is **C + Y** (programmatic graph, checkpointed). The most requested combination in the Airflow/n8n ecosystem is **B + Y** (declarative, checkpointed). Both converge on the checkpointed execution model.

## Interactions with Existing ADRs

- **ADR-0025 (shared context KV).** `mesh-context` is already the natural home for workflow state. A `mesh-workflows` bucket or a `workflow:*` key prefix would avoid polluting application context.
- **ADR-0027 (object store).** Large intermediate outputs (documents, transcripts, embeddings) would be stored as object-store artifacts referenced from checkpoints, not inlined.
- **ADR-0034 (subscribe and managed callback).** Workflows that wait on async events (e.g., "pause until user approval arrives on `approvals.*`") would use the managed callback to resume. This is a natural extension, not a conflict.
- **ADR-0024 (streaming handlers).** Streaming nodes need thought: do we checkpoint every chunk, only the final result, or buffer the stream and checkpoint on completion? Default "checkpoint on completion" is simplest but loses mid-stream state.
- **ADR-0035 (control plane).** A paused or disabled agent inside a running workflow raises routing questions: does the workflow wait, fail fast, or reroute to a replacement?

## Open Questions

- **Is orchestration SDK-level or plugin-level?** The Mesh Plugins idea suggests this is exactly the kind of pattern that belongs in a plugin (`agentmesh-workflow` or similar), not in the core SDK. The SDK provides primitives (KV, subscribe, call); the plugin provides the orchestration runtime. Does keeping it out of the core preserve the "fabric, not framework" positioning, or does leaving orchestration to plugins fragment the DX?
- **Declarative vs. programmatic, or both?** If both, which is canonical and which is a serialization?
- **Non-determinism and replay.** LLM calls are non-deterministic. Replay semantics need a policy: replay recorded outputs (cached), re-execute and overwrite, or re-execute and compare? Each has different use cases (debugging vs. reproducing vs. regression testing).
- **Checkpoint granularity.** Per-node, per-chunk for streaming, per-tool-call inside an agent? Finer granularity gives better replay fidelity at the cost of KV write volume.
- **Human-in-the-loop.** Is "pause and wait for external input" a first-class concept (a special node type) or just another agent that blocks on a subscribe? The latter is more elegant but harder to reason about in YAML.
- **Workflow versioning.** When the YAML changes while a workflow is mid-flight, does it finish on the old version or adopt the new one? This is a known hard problem (Temporal solves it with versioning markers).
- **Failure semantics.** Retry policies, timeouts, dead-letter routing, compensation steps? YAML surface needs to cover these without becoming a BPMN-level tome.
- **Visualization.** Does a declarative YAML workflow imply we also ship a visualizer? Airflow's UI and n8n's canvas are large pieces of their value proposition. OAM has no admin UI yet (see ADR-0035).
- **Overlap with A2A federation.** When a workflow calls a federated agent across an A2A boundary, where does the checkpoint live? Local side only, or mirrored to the remote side?
- **Phase fit.** This is clearly post-Phase 1. Is it Phase 2 (alongside OTel and Compose) or Phase 3+ (alongside admin UI)?

## Prior Art to Study

- **LangGraph.** Checkpointed graph with Python DSL, SQLite/Postgres backends, time-travel debugging. Strongest reference for the `C + Y` cell.
- **Temporal.** Workflow-as-code with full event sourcing, deterministic replay, versioning. Strongest reference for the `Z` column.
- **Airflow / Argo / Prefect.** Declarative DAGs with varying degrees of dynamism. Reference for the `B` row.
- **n8n / Windmill / Pipedream.** Visual and YAML-declared workflows with low-code focus. Reference for the operator-facing DX.
- **Ray Workflows.** Checkpointed workflows built on an actor system. Relevant because OAM agents are actor-like.
