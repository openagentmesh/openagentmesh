# OAM and A2A

A2A (Agent-to-Agent) is Google's protocol for cross-organization agent federation. It defines how agents from different companies discover and invoke each other over HTTP, using a standard Agent Card format.

OAM is designed to work **with** A2A, not against it. The relationship is straightforward:

- **OAM** = internal fabric (agents within your organization, over NATS)
- **A2A** = external bridge (agents across organizations, over HTTP)

```python
from openagentmesh import AgentMesh

mesh = AgentMesh("nats://mesh.company.com:4222")
contract = await mesh.contract("summarizer")

# Project to A2A Agent Card for external federation
agent_card = contract.to_agent_card(url="https://api.company.com/agents/summarizer")
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
    "type": "agent",
    "channel": "nlp",
    "subject": "mesh.agent.nlp.summarizer",
    "sla": { "expected_latency_ms": 5000, "timeout_ms": 30000 }
  }
}
```

The `to_agent_card()` method is a **thin projection**, not a conversion. It strips the `x-agentmesh` extension and injects the `url` field -- the only A2A field that isn't stored in the OAM registry, because it's gateway-provided at the federation boundary.

## The `url` field

Internally, agents are addressed by NATS subject (`mesh.agent.nlp.summarizer`). They don't have HTTP URLs. When you expose an agent externally via an A2A-compatible gateway, the gateway assigns the URL:

```python
# Internal: no URL needed
contract = await mesh.contract("summarizer")

# External: gateway provides the URL
card = contract.to_agent_card(url="https://gateway.company.com/agents/summarizer")

# Without a URL, the card is still valid -- just not routable over HTTP
card_no_url = contract.to_agent_card()
```

## When to use which

| Scenario | Protocol |
|----------|----------|
| Agents within your team | OAM |
| Agents across teams in the same org | OAM |
| Agents exposed to partner organizations | A2A (via `to_agent_card()`) |
| Agents on a public agent directory | A2A (via `to_agent_card()`) |

!!! info "One contract, two protocols"
    You write one agent, register one contract, and project it to A2A format only at the boundary where internal meets external. No duplication, no drift.

For how OAM relates to MCP, see [OAM and MCP](oam-and-mcp.md). For the technology choices behind OAM, see [Technology Stack](technology.md).
