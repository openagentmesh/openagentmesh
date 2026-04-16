# ADR-0004: Schema quality tiers for external MCP tool intake

- **Type:** architecture
- **Date:** 2026-04-11
- **Status:** accepted
- **Source:** km/notes/20260411_On JSON-RPC and MCP bridges.md

## Context

External MCP servers have wildly inconsistent schema quality, from fully valid JSON Schema to empty objects to completely missing `inputSchema` fields. MCP defines no output schema at all. The bridge needs a strategy for handling this spectrum.

## Decision

Implement an intake normalization pipeline with four quality tiers:

- **validated:** passes JSON Schema meta-schema check, used as-is
- **normalized:** partial schema (missing `type`, `required`), SDK fills gaps
- **inferred:** empty or missing, SDK generates passthrough `{"type": "object", "additionalProperties": true}` with warning
- **overridden:** developer supplied their own Pydantic model via `schema_overrides`

The `schema_quality` field surfaces in the contract under `x-agentmesh` and in the catalog, enabling filtering: `mesh.catalog(min_schema_quality="normalized")`.

Output side uses a normalized `MCPToolResult` envelope (content blocks typed as text/image/resource) since MCP results are inherently untyped. Developer-supplied `output_model` overrides enable Pydantic validation on the mesh side.

## Risks and Implications

- `inferred` tier tools are usable but risky; callers get no validation. The `schema_quality` field and `min_schema_quality` filter make this explicit rather than silent.
- `schema_overrides` per tool adds API surface. Worth it for production use of poorly-documented MCP servers.
- `on_bad_schema` policy ("warn" | "skip" | "raise") gives teams control over strictness.
