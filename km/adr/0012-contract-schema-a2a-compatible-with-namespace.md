# ADR-0012: Contract schema as A2A-compatible with x-agentmesh namespace

- **Type:** protocol
- **Date:** 2026-04-03
- **Status:** documented
- **Source:** .specstory/history/2026-04-03_22-03-07Z.md

## Context

The agent contract schema needed to be designed. The question was how to relate it to the A2A Agent Card format: strict superset, subset, or structurally translatable.

## Decision

Store contracts as structurally compatible with A2A Agent Cards. A2A-standard fields (`name`, `description`, `version`, `capabilities`, `skills`) live at the top level. AgentMesh-specific fields (`channel`, `subject`, `sla`, `error_schema`, `metadata`) live under an `x-agentmesh` namespace extension block.

The `url` field is the only A2A field not stored in the registry; it is gateway-provided at federation time. `.to_agent_card(url=None)` is a thin projection that injects the URL if provided, not a deep conversion.

## Alternatives Considered

- **Strict A2A superset with mixed fields.** Rejected; AgentMesh-specific fields scattered alongside A2A fields makes the boundary unclear.
- **Separate internal format with A2A conversion.** Rejected; unnecessary complexity when the schemas are naturally compatible.

## Risks and Implications

- Tied to the A2A Agent Card format. If A2A evolves significantly, the contract schema must track those changes.
- The `x-agentmesh` namespace is a convention, not enforced by A2A. External tools consuming the contract may ignore it.
- Gateway (Phase 4) can produce compliant A2A Agent Cards with minimal transformation.