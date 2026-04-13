# Contracts

Every agent publishes a typed contract describing its capabilities, input/output schemas, and metadata. Contracts are the foundation of runtime discovery.

## Schema Format

Contracts are a superset of the [A2A Agent Card](https://google.github.io/A2A/) format. A2A-standard fields sit at the top level; AgentMesh-specific fields live under `x-agentmesh`.

```json
{
  "name": "summarizer",
  "description": "Summarizes text to a target length.",
  "version": "1.0.0",
  "capabilities": { "streaming": false, "pushNotifications": true },
  "defaultInputModes": ["application/json"],
  "defaultOutputModes": ["application/json"],
  "skills": [
    {
      "id": "summarizer",
      "name": "Summarize text",
      "description": "Summarizes text to a target length.",
      "tags": ["text", "summarization"],
      "inputSchema": { ... },
      "outputSchema": { ... }
    }
  ],
  "x-agentmesh": {
    "type": "agent",
    "channel": "nlp",
    "subject": "mesh.agent.nlp.summarizer",
    "sla": {
      "expected_latency_ms": 5000,
      "timeout_ms": 30000,
      "retry_policy": "idempotent",
      "max_retries": 2
    }
  }
}
```

## Auto-Generation

Contracts are generated automatically from your handler's type hints:

```python
@mesh.agent(name="summarizer", channel="nlp",
            description="Summarizes text to a target length.")
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...
```

Pydantic v2 models produce JSON Schemas for `inputSchema` and `outputSchema`. The `description` field is written for LLM consumption — it should state what the agent does, what inputs it handles, and what it should **not** be used for.

## LLM Tool Conversion

Convert any contract to an LLM-ready tool definition:

```python
contract = await mesh.contract("summarizer")

contract.to_openai_tool()      # OpenAI function calling format
contract.to_anthropic_tool()   # Anthropic tool use format
contract.to_generic_tool()     # Generic JSON Schema format
contract.to_agent_card()       # A2A Agent Card format
```

## A2A Compatibility

The only A2A field not stored in the registry is `url` — it's gateway-provided at federation time:

```python
contract.to_agent_card(url="https://api.company.com/agents/summarizer")
```
