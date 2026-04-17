# OAM and A2A

A2A (Agent-to-Agent) is Google's protocol for cross-organization agent federation. It defines how agents from different companies discover and invoke each other over HTTP, using a standard Agent Card format.

OAM is designed to work **with** A2A, not against it. The relationship is straightforward:

- **OAM** = internal fabric (agents within your organization, over NATS)
- **A2A** = external bridge (agents across organizations, over HTTP)

```python
from openagentmesh import AgentMesh

mesh = AgentMesh("nats://mesh.company.com:4222")
contract = await mesh.contract("summarizer")

# The contract is already A2A-compatible.
# A future to_agent_card() method will project it
# with a url injected at federation boundaries.
```

## Contract compatibility

OAM contracts are an **A2A-compatible superset**. The contract schema places A2A-standard fields at the top level and OAM-specific extensions under `x-agentmesh`:

```json
{
  "name": "summarizer",
  "description": "Summarizes input text...",
  "version": "1.0.0",
  "capabilities": { "streaming": false, "pushNotifications": true },
  "skills": [
    {
      "id": "summarizer",
      "name": "Summarize text",
      "description": "...",
      "tags": ["text", "summarization"],
      "inputSchema": { },
      "outputSchema": { }
    }
  ],
  "x-agentmesh": {
    "channel": "nlp",
    "subject": "mesh.agent.nlp.summarizer",
    "tags": ["text", "summarization"]
  }
}
```

The projection from OAM contract to A2A Agent Card is a **thin operation**: strip the `x-agentmesh` extension and inject the `url` field. The `url` is the only A2A field not stored in the OAM registry, because it's gateway-provided at the federation boundary.

## The `url` field

Internally, agents are addressed by NATS subject (`mesh.agent.nlp.summarizer`). They don't have HTTP URLs. When you expose an agent externally via an A2A-compatible gateway, the gateway assigns the URL.

The contract's `to_registry_json()` method already produces A2A-compatible JSON. A dedicated `to_agent_card()` convenience method is planned.

## When to use which

| Scenario | Protocol |
|----------|----------|
| Agents within your team | OAM |
| Agents across teams in the same org | OAM |
| Agents exposed to partner organizations | A2A (via contract projection) |
| Agents on a public agent directory | A2A (via contract projection) |

!!! info "One contract, two protocols"
    You write one agent, register one contract, and project it to A2A format only at the boundary where internal meets external. No duplication, no drift.

For how OAM relates to MCP, see [OAM and MCP](oam-and-mcp.md). For the technology choices behind OAM, see [Technology Stack](technology.md).
