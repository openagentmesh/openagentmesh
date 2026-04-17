# Architecture Decision Records

Design decisions made during OpenAgentMesh development. Each ADR captures the context, decision, and consequences.

Status values follow the [Documentation Driven Development pipeline](../../CLAUDE.md#workflow-documentation-driven-development):
`discussion` -> `spec` -> `test` -> `implemented` -> `documented` -> `superseded by ADR-NNNN`

| ADR | Decision | Status | Branch |
|-----|----------|--------|--------|
| [ADR-0001](0001-reject-json-rpc-as-internal-message-standard.md) | Reject JSON-RPC as internal message standard | discussion | |
| [ADR-0002](0002-bidirectional-mcp-bridge-design.md) | Bidirectional MCP bridge design | discussion | |
| [ADR-0003](0003-mcp-export-flag-as-boolean.md) | MCP export flag as boolean | spec | |
| [ADR-0004](0004-schema-quality-tiers-for-mcp-intake.md) | Schema quality tiers for MCP intake | discussion | |
| [ADR-0005](0005-streaming-wire-protocol.md) | Streaming wire protocol | documented | feature/streaming-protocol |
| [ADR-0006](0006-sla-gating-for-mcp-export.md) | SLA gating for MCP export | spec | |
| [ADR-0007](0007-use-plain-pydantic-not-pydanticai.md) | Use plain Pydantic, not PydanticAI | discussion | |
| [ADR-0008](0008-dx-first-development-strategy.md) | DX-first development strategy | documented | |
| [ADR-0009](0009-catalog-as-sole-discovery-primitive.md) | Catalog as sole discovery primitive | discussion | |
| [ADR-0010](0010-pull-object-store-into-phase-1.md) | Pull object store into Phase 1 | discussion | |
| [ADR-0011](0011-use-uv-with-ruff-and-ty.md) | Use uv with ruff and ty | documented | |
| [ADR-0012](0012-contract-schema-a2a-compatible-with-namespace.md) | Contract schema: A2A-compatible with namespace | discussion | |
| [ADR-0013](0013-hyphenated-kv-bucket-names.md) | Hyphenated KV bucket names | discussion | |
| [ADR-0014](0014-single-key-denormalized-catalog.md) | Single-key denormalized catalog | discussion | |
| [ADR-0015](0015-prefer-path-nats-server-over-download.md) | Prefer PATH nats-server over download | discussion | |
| [ADR-0016](0016-disconnect-advisories-for-instant-failure-detection.md) | Disconnect advisories for instant failure detection | discussion | |
| [ADR-0017](0017-rebrand-to-openagentmesh.md) | Rebrand to OpenAgentMesh | discussion | |
| [ADR-0018](0018-use-zensical-for-documentation.md) | Use Zensical for documentation | documented | |
| [ADR-0019](0019-differentiate-oam-from-mcp-on-topology.md) | Differentiate OAM from MCP on topology, not sync/async | documented | |
| [ADR-0020](0020-distinguish-catalog-filtering-from-nats-wildcards.md) | Distinguish SDK catalog filtering from NATS subject wildcards | discussion | |
| [ADR-0021](0021-consolidate-jetstream-bucket-specification.md) | Consolidate JetStream bucket specification | discussion | |
| [ADR-0022](0022-local-as-async-context-manager.md) | Make `AgentMesh.local()` an async context manager for tests and demos | documented | feature/core-sdk |
| [ADR-0023](0023-llm-cost-model-and-usage-attribution.md) | LLM cost model and usage attribution | spec | |
| [ADR-0023b](0023-single-decorator-with-type-taxonomy.md) | Single `@mesh.agent` decorator with type taxonomy _(numbering conflict, to be renumbered)_ | type taxonomy superseded by ADR-0031 | |
| [ADR-0024](0024-streaming-or-buffered-handler-contract.md) | Streaming or buffered as a per-agent handler choice, both typed | documented | feature/core-sdk |
| [ADR-0025](0025-public-api-for-shared-context-kv.md) | Public API for shared context KV (`mesh-context` bucket) | discussion | |
| [ADR-0026](0026-handler-access-to-mesh-from-separate-modules.md) | Handler access to mesh services from separate modules | discussion | |
| [ADR-0027](0027-object-store-workspace-lifecycle-and-scoping.md) | Object Store workspace lifecycle and scoping | discussion | |
| [ADR-0028](0028-catalog-entry-pydantic-model.md) | `mesh.catalog()` returns typed `CatalogEntry` Pydantic models | documented | feature/core-sdk |
| [ADR-0029](0029-async-callback-consumption-api.md) | Async callback consumption API | discussion | |
| [ADR-0030](0030-agentspec-model-for-decorator.md) | `AgentSpec` Pydantic model as single decorator argument | documented | feature/core-sdk |
| [ADR-0031](0031-capabilities-over-type-taxonomy.md) | Capabilities over type taxonomy (supersedes ADR-0023b type portion) | documented | feature/core-sdk |
| [ADR-0032](0032-catalog-change-subscription.md) | Catalog change subscription for client-side capability cache | documented | feature/streaming-protocol |
| [ADR-0033](0033-cli-surface-and-phase-1-scope.md) | CLI surface and Phase 1 scope | spec | worktree-oam-cli |
