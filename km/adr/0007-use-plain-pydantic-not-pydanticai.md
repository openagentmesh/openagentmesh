# ADR-0007: Use plain Pydantic v2, not PydanticAI, as SDK foundation

- **Type:** architecture
- **Date:** 2026-04-04
- **Status:** accepted
- **Source:** .specstory/history/2026-04-04_20-03-02Z.md

## Context

PydanticAI is an agent framework built on Pydantic that handles LLM orchestration, tool routing, and structured outputs. The question was whether it should be used as a foundation for the AgentMesh SDK.

## Decision

Use plain Pydantic v2 only. PydanticAI is a mismatch because:

1. **Different abstraction layer.** PydanticAI is an agent framework (LLM orchestration). AgentMesh is a transport layer ("the LAN of agents"). These are orthogonal.
2. **Violates "no framework adapters."** The spec says the handler body is the developer's territory. Coupling to PydanticAI forces an opinion on agent internals.
3. **Unnecessary dependency weight.** PydanticAI pulls in LLM client libraries. AgentMesh's hard deps should only be `nats-py` and `pydantic`.
4. **Pydantic v2 already covers everything:** `BaseModel` for validation, `.model_json_schema()` for contracts, `get_type_hints()` for introspection.

PydanticAI is a valid choice *inside* a handler function; that's a good `examples/` showcase, not a core dependency.

## Risks and Implications

- Users wanting PydanticAI integration must write a thin bridge function themselves. This is by design; the handler is their territory.
- The SDK stays lightweight with only two hard dependencies: `nats-py` and `pydantic`.
