# ADR-0010: Pull object store into Phase 1

- **Type:** strategy
- **Date:** 2026-04-06
- **Status:** documented
- **Source:** .specstory/history/2026-04-06_19-52-50Z.md

## Context

The JetStream Object Store was originally planned for Phase 2+. It enables shared artifact storage between agents (binary files, large payloads). The question was whether to include it in the demo/walkthrough code early.

## Decision

Add object store support to Phase 1. It should be part of the demo or walkthrough code to showcase the shared context capability from the start. The implementation uses `mesh-artifacts` as the Object Store bucket name and `mesh-context` for shared KV context data.

## Risks and Implications

- Expands Phase 1 scope. The object store itself is thin (JetStream Object Store is a NATS primitive), but it needs lifecycle management (bucket creation on startup, cleanup on shutdown).
- Resolves the open question in `km/ideas.md` about "Shared memory/context": the object store is the answer for binary artifacts.
- Demo code must show a compelling use case (e.g., agents sharing files/results) to justify the early inclusion.

## Code Sample

The [Parallel RAG Indexing](../../docs/cookbook/parallel-rag-indexing.md) cookbook recipe serves as the DX contract. It demonstrates `mesh.workspace.put()`, `mesh.workspace.get()`, and `mesh.workspace.delete()` in a realistic scenario: an orchestrator uploads a document, fans out indexing to multiple agents via queue groups, each agent reads from the ObjectStore and writes embeddings to ChromaDB.
