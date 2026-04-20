# Architecture Decision Records

Design decisions made during OpenAgentMesh development. Each ADR captures the context, decision, and consequences.

Status values follow the [Documentation Driven Development pipeline](../../CLAUDE.md#workflow-documentation-driven-development):
`discussion` -> `spec` -> `test` -> `implemented` -> `documented` -> `superseded by ADR-NNNN`

| ADR | Decision | Status | Branch |
|-----|----------|--------|--------|
| [ADR-0001](0001-reject-json-rpc-as-internal-message-standard.md) | Reject JSON-RPC as internal message standard | documented | |
| [ADR-0002](0002-bidirectional-mcp-bridge-design.md) | Bidirectional MCP bridge design | spec | |
| [ADR-0003](0003-mcp-export-flag-as-boolean.md) | MCP export flag as boolean | spec | |
| [ADR-0004](0004-schema-quality-tiers-for-mcp-intake.md) | Schema quality tiers for MCP intake | discussion | |
| [ADR-0005](0005-streaming-wire-protocol.md) | Streaming wire protocol | documented | feature/streaming-protocol |
| [ADR-0006](0006-sla-gating-for-mcp-export.md) | SLA gating for MCP export | spec | |
| [ADR-0007](0007-use-plain-pydantic-not-pydanticai.md) | Use plain Pydantic, not PydanticAI | documented | |
| [ADR-0008](0008-dx-first-development-strategy.md) | DX-first development strategy | documented | |
| [ADR-0009](0009-catalog-as-sole-discovery-primitive.md) | Catalog as sole discovery primitive | documented | |
| [ADR-0010](0010-pull-object-store-into-phase-1.md) | Pull object store into Phase 1 | documented | feature/object-store |
| [ADR-0011](0011-use-uv-with-ruff-and-ty.md) | Use uv with ruff and ty | documented | |
| [ADR-0012](0012-contract-schema-a2a-compatible-with-namespace.md) | Contract schema: A2A-compatible with namespace | documented | |
| [ADR-0013](0013-hyphenated-kv-bucket-names.md) | Hyphenated KV bucket names | documented | |
| [ADR-0014](0014-single-key-denormalized-catalog.md) | Single-key denormalized catalog | documented | |
| [ADR-0015](0015-prefer-path-nats-server-over-download.md) | Prefer PATH nats-server over download | implemented | |
| [ADR-0016](0016-disconnect-advisories-for-instant-failure-detection.md) | Disconnect advisories for instant failure detection | spec | |
| [ADR-0017](0017-rebrand-to-openagentmesh.md) | Rebrand to OpenAgentMesh | documented | |
| [ADR-0018](0018-use-zensical-for-documentation.md) | Use Zensical for documentation | documented | |
| [ADR-0019](0019-differentiate-oam-from-mcp-on-topology.md) | Differentiate OAM from MCP on topology, not sync/async | documented | |
| [ADR-0020](0020-distinguish-catalog-filtering-from-nats-wildcards.md) | Distinguish SDK catalog filtering from NATS subject wildcards | documented | |
| [ADR-0021](0021-consolidate-jetstream-bucket-specification.md) | Consolidate JetStream bucket specification | documented | |
| [ADR-0022](0022-local-as-async-context-manager.md) | Make `AgentMesh.local()` an async context manager for tests and demos | documented | feature/core-sdk |
| [ADR-0023](0023-llm-cost-model-and-usage-attribution.md) | LLM cost model and usage attribution | spec | |
| [ADR-0023b](0023-single-decorator-with-type-taxonomy.md) | Single `@mesh.agent` decorator with type taxonomy | superseded by ADR-0031 | |
| [ADR-0024](0024-streaming-or-buffered-handler-contract.md) | Streaming or buffered as a per-agent handler choice, both typed | documented | feature/core-sdk |
| [ADR-0025](0025-public-api-for-shared-context-kv.md) | Public API for shared context KV (`mesh-context` bucket) | documented | |
| [ADR-0026](0026-handler-access-to-mesh-from-separate-modules.md) | Handler access to mesh services from separate modules | documented | |
| [ADR-0027](0027-object-store-workspace-lifecycle-and-scoping.md) | Object Store workspace lifecycle and scoping | discussion | |
| [ADR-0028](0028-catalog-entry-pydantic-model.md) | `mesh.catalog()` returns typed `CatalogEntry` Pydantic models | documented | feature/core-sdk |
| [ADR-0029](0029-async-callback-consumption-api.md) | Async callback consumption API | superseded by ADR-0034 | |
| [ADR-0030](0030-agentspec-model-for-decorator.md) | `AgentSpec` Pydantic model as single decorator argument | documented | feature/core-sdk |
| [ADR-0031](0031-capabilities-over-type-taxonomy.md) | Capabilities over type taxonomy (supersedes ADR-0023b type portion) | documented | feature/core-sdk |
| [ADR-0032](0032-catalog-change-subscription.md) | Catalog change subscription for client-side capability cache | documented | feature/streaming-protocol |
| [ADR-0033](0033-cli-surface-and-phase-1-scope.md) | CLI surface and Phase 1 scope | documented | worktree-oam-cli |
| [ADR-0034](0034-subscribe-pubsub-and-managed-async-callback.md) | Subscribe primitive, publisher emission, and managed async callback | documented | |
| [ADR-0035](0035-control-plane-for-agent-channel-scoping.md) | Control plane for agent and channel scoping | discussion | |
| [ADR-0036](0036-orchestration-declarative-workflows-and-checkpointing.md) | Orchestration: declarative workflows and checkpointing | discussion | |
| [ADR-0037](0037-oam-scope-per-agent-visibility-and-reachability.md) | OAM scope: per-agent visibility and reachability | spec | |
| [ADR-0038](0038-nats-authentication-and-credential-management.md) | NATS authentication and credential management | spec | |
| [ADR-0039](0039-contract-to-llm-tool-conversion.md) | Contract-to-LLM-tool conversion (`to_tool_schema`, `to_openai_tool`, `to_anthropic_tool`) | documented | feature/tool-conversion |
| [ADR-0040](0040-death-notice-fast-fail-for-in-flight-requests.md) | Death-notice triggered fast failure for in-flight requests | discussion | |
| [ADR-0041](0041-cli-demos-as-canonical-code-samples.md) | CLI demos as canonical code samples (single source for docs, tests, CLI) | superseded by ADR-0045 | feature/cli-demos |
| [ADR-0042](0042-watcher-agent-pattern.md) | Watcher agent pattern (fourth capability combination) | documented | feature/watcher-agent |
| [ADR-0043](0043-trigger-handler-pattern.md) | Trigger handler pattern (invocable, no input) | documented | feature/watcher-agent |
| [ADR-0044](0044-handler-shape-rename-responder-streamer.md) | Rename handler shapes to Responder/Streamer | documented | feature/handler-shape-rename |
| [ADR-0045](0045-unlink-cookbook-from-demos.md) | Unlink cookbook docs from demo modules (supersedes ADR-0041) | implemented | |
