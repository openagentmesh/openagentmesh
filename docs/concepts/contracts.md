# Contracts

Every agent publishes a typed contract describing its capabilities, input/output schemas, and metadata. Contracts are the foundation of runtime discovery.

## Schema Format

Contracts are a superset of the [A2A Agent Card](https://google.github.io/A2A/) format. A2A-standard fields sit at the top level; AgentMesh-specific fields live under `x-agentmesh`.

```json
{
  "name": "nlp.summarizer",
  "description": "Summarizes text to a target length.",
  "version": "1.0.0",
  "capabilities": { "streaming": false, "invocable": true },
  "skills": [
    {
      "id": "nlp.summarizer",
      "name": "nlp.summarizer",
      "description": "Summarizes text to a target length.",
      "tags": ["text", "summarization"],
      "inputSchema": { ... },
      "outputSchema": { ... }
    }
  ],
  "x-agentmesh": {
    "subject": "mesh.agent.nlp.summarizer",
    "tags": ["text", "summarization"],
    "registered_at": "2026-04-17T10:00:00Z"
  }
}
```

The dotted `name` carries both the channel hierarchy and the leaf identifier (ADR-0049).

## Auto-Generation

Contracts are generated automatically from your `AgentSpec` and handler type hints:

```python
spec = AgentSpec(
    name="nlp.summarizer",
    description="Summarizes text to a target length.",
)

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...
```

Pydantic v2 models produce JSON Schemas for `inputSchema` and `outputSchema`. The `description` field is written for LLM consumption: it should state what the agent does, what inputs it handles, and what it should **not** be used for.

Capabilities (`invocable`, `streaming`) are inferred from the handler shape. No explicit declaration needed.

## Using Contracts for LLM Tool Injection

Fetch a contract and use its schemas to build tool definitions for your LLM provider:

```python
contract = await mesh.contract("nlp.summarizer")

# Build tool definition
tool = {
    "name": contract.name,
    "description": contract.description,
    "input_schema": contract.input_schema,
}
```

## A2A Compatibility

The contract schema is a superset of the A2A Agent Card. The only A2A field not stored in the registry is `url`; it's context-dependent and injected at federation boundaries.
