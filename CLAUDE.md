# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

- `km/` -- Internal knowledge management. Rough specs, ideas, and ADRs (`km/adr/`). Working material, not user-facing.
- `docs/` -- Official documentation (Zensical/MkDocs). Source of truth for users. Code samples here drive development (see Workflow below).
- `docs/cookbook/` -- Practical recipes with embedded code samples. These code samples are the DX contract.
- `km/adr/index.md` -- ADR tracking index with status per decision.
- `tests/cookbook/` -- Executable versions of docs/cookbook code samples, wrapped in pytest. Thin wrappers: same code, plus assertions and fixtures (e.g. `AgentMesh.local()`).

## What OpenAgentMesh Is

OpenAgentMesh (OAM) is a protocol and Python SDK for multi-agent interation. Agents register on a shared message bus, publish typed contracts, and discover/invoke each other at runtime without direct coupling. Analogous to a service mesh (Istio/Linkerd) but for AI agents.

**Positioning:** "The fabric for multi-agent systems, with the simplicity of a REST endpoint". Internal fabric (vs. MCP for tools, A2A for cross-org federation).

**Naming convention:** Project/brand is "OpenAgentMesh" / "OAM". Code class name stays `AgentMesh` for ergonomics (`from openagentmesh import AgentMesh`).

## Architecture

For full details, see the official docs (`docs/`):

- **Core abstractions:** `docs/concepts/agents.md` (AgentMesh class, @mesh.agent decorator, handler shape inference)
- **Channels and discovery:** `docs/concepts/channels.md`, `docs/concepts/discovery.md`
- **Contracts and registry:** `docs/concepts/contracts.md` (two-tier KV: catalog + per-agent registry)
- **Invocation patterns:** `docs/concepts/invocation.md` (call, stream, send, subscribe)
- **Protocol and subjects:** `docs/architecture/protocol.md`, `docs/architecture/subjects.md`
- **Message envelope:** `docs/architecture/envelope.md`
- **Errors:** `docs/concepts/errors.md`
- **API reference:** `docs/api/agentmesh.md`, `docs/api/contract.md`, `docs/api/cli.md`
- **Quickstart:** `docs/quickstart.md`

Internal specs in `km/` contain deeper rationale and rough design notes:
- `km/agentmesh-spec.md` -- Protocol specification (most detailed)
- `km/agentmesh-developer-experience.md` -- SDK design and DX philosophy
- `km/agentmesh-registry-and-discovery.md` -- Registry, catalog, discovery patterns
- `km/agentmesh-liveness-and-failure.md` -- Liveness, failure modes, death notices
- `km/ideas.md` -- Unresolved design questions and future ideas

## Documentation

- **Tool:** Zensical (Rust-based successor to Material for MkDocs). Reads `mkdocs.yml` natively.
- **Source:** `docs/` (Markdown). **Build output:** `site/` (gitignored).
- **Dev server:** `uv run zensical serve`
- **See:** ADR-0018

## Key Design Decisions

- **Pydantic v2** for input/output validation and JSON Schema generation. Type hints on the handler function are used for introspection -- explicit `input_model`/`output_model` parameters are the fallback.
- **Queue groups** for every invocation subscription -- native NATS load balancing enables multiple instances of the same agent with no config changes.
- **CAS on catalog updates** -- concurrent registration retries read-modify-write until KV revision matches. Catalog may be momentarily stale (milliseconds); `mesh.contract()` is authoritative.
- **No framework adapters** -- the handler function body is the developer's territory. Wrapping existing agents is a thin bridge function, not an SDK concern.
- **Two-step discovery at scale** -- `catalog()` for LLM-based selection (20–30 tokens/agent), then `contract()` for targeted schema fetch. No RAG or vector DB needed up to ~500 agents.
- **Embedded NATS** (`AgentMesh.local()`) is an async context manager that downloads the NATS binary to `~/.agentmesh/bin/`, runs as a subprocess with JetStream + KV pre-configured. Scoped to tests and demos; the standard dev workflow uses `agentmesh up` + `AgentMesh()`.

## Workflow: Documentation Driven Development

OAM is a protocol and SDK where the primary value is developer experience. The documentation is the source of truth for users: it teaches them how to use the protocol and SDK through both explanation and code samples. Those code samples are the pivot point of the entire development workflow.

### The pipeline

```
Brainstorm -> Shape -> ADR (with code sample) -> Test -> Implement -> Finalize docs
```

1. **Brainstorm.** Discuss ideas, explore trade-offs. Record rough notes in `km/notes/` or spec files in `km/`. No commitment yet.

2. **Shape.** When an idea is "shaped" enough (from the Shape Up methodology: clear problem, rough solution, bounded scope, identified rabbit holes), crystallize it into an ADR in `km/adr/`. The ADR must include a **code sample** showing how the feature should look from the user's perspective. This code sample is the DX contract: if it looks awkward, fix the API design before proceeding.

3. **Test.** Extract the ADR's code sample into an executable test under `tests/` (pytest). The test is a thin wrapper: same code as the doc sample, plus assertions and fixtures. Tests must fail (red) since there is no implementation yet.

4. **Implement.** Write the minimum code to make the tests pass (green). Follow TDD: red, green, refactor. Commits are atomic per logical unit, not one big commit at the end.

5. **Finalize docs.** Update `docs/cookbook/` and any other relevant pages in `docs/` to reflect the implemented feature. The code samples in docs must match what actually works. Duplication between `docs/cookbook/` and `tests/cookbook/` is intentional: docs stay clean (no pytest noise), tests stay executable.

### ADR as work item

Each ADR in `km/adr/` is a trackable unit of work. The **Status** field in `km/adr/index.md` reflects where the ADR sits in the pipeline:

| Status | Meaning |
|--------|---------|
| `discussion` | Idea identified, not yet shaped |
| `spec` | Shaped into ADR with code sample |
| `test` | Code sample extracted into failing tests |
| `implemented` | Tests pass, code exists |
| `documented` | Official docs in `docs/` updated |
| `superseded by ADR-NNNN` | Replaced by a later decision |

**Rules:**
- An ADR cannot move to `test` without a code sample in the ADR body.
- An ADR cannot move to `documented` without passing tests.
- The `accepted` status is legacy; treat as `implemented` or `documented` depending on whether docs exist.

## Parallel Development with Worktrees

Multiple features can be implemented simultaneously using git worktrees. Each worktree is an isolated workspace with its own branch, virtual environment, and working copy.

### Isolation rule

- **Code changes only happen inside worktrees.** All modifications to `src/`, `tests/`, `docs/`, and dependency files (`pyproject.toml`, `uv.lock`) must be in a worktree branch, never directly on `main`.
- **`main` is the thinking space.** Direct work on `main` is limited to `km/` (ADRs, specs, notes, brainstorming), `CLAUDE.md`, and project config files.

### When to create a worktree

A worktree is created when an ADR (or group of related ADRs) reaches `spec` status and is ready for the test-implement-document cycle. Brainstorming, shaping, and ADR writing happen on `main`. Worktrees are an implementation tool, not a design tool.

### Claim protocol

Before creating a worktree, the session must claim the target ADRs in `km/adr/index.md` by filling in the **Branch** column. This makes active work visible to all sessions and prevents overlap. If a target ADR is already claimed by an active branch, flag the conflict to the user before proceeding.

### Branch and directory conventions

- Worktrees live in `.worktrees/` (gitignored).
- Branch naming: `feature/<short-name>` (descriptive slug, not ADR numbers).
- A branch can span multiple related ADRs.

### PR workflow

When implementation is complete (tests pass, docs updated), push the branch and open a draft PR referencing the implemented ADRs. The user reviews and merges on their schedule. After merge, clean up the worktree; the branch name stays in the ADR index as a historical record.

### Detailed procedures

Step-by-step procedures for each stage of the parallel workflow are in `km/workflow/`:
- `km/workflow/starting-a-session.md`
- `km/workflow/during-a-session.md`
- `km/workflow/finishing-a-session.md`
- `km/workflow/after-merge.md`

## Development Phases

The spec defines four phases. **Phase 1 is the current target:**

**Phase 1 (MVP):** `AgentMesh` class, `@mesh.agent` decorator (with type inference from handler shape), Pydantic v2 validation, `mesh.call()` / `mesh.stream()` / `mesh.send()` / `mesh.subscribe()` / `mesh.discover()`, lifecycle management, `AgentMesh.local()` async context manager for tests, `agentmesh up` CLI, "Hello World" in <30 lines.

Not in Phase 1: middleware hooks, OTel, Docker Compose tier, admin UI, TypeScript SDK, spawning from specs.

## Contract Schema Reference

The contract schema is a superset of the A2A Agent Card format. A2A fields at top level; OAM-specific fields under `x-agentmesh`. Full schema and examples in `docs/api/contract.md`. Key points:

- `x-agentmesh.type`: `"agent"` (streaming, LLM-powered), `"tool"` (buffered, deterministic), `"publisher"` (events, not invocable), `"subscriber"` (reserved).
- `capabilities.streaming`: inferred from handler shape (return vs. yield).
- `url` field is not stored in registry; injected by gateway at federation time. `.to_agent_card(url=None)` is a thin projection.
- `description` is consumed by LLMs for tool selection: must state what the agent does, what inputs it handles, when NOT to use it.


## Behavioral notes
- Act as an expert advisor, always evaluating the user's idea critically: surface potenetial problems and push back when there are significant risks. Seek and ensure alignment proactively before proceeding with any change.
- Do not add claude as co-author of commits.