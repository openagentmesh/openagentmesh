# Understanding OpenAgentMesh

This section explains **why** OpenAgentMesh exists, how it fits alongside other protocols like MCP and A2A, and the technology choices behind it.

If you want to jump straight into code, start with the [Quickstart](../quickstart.md) instead. Come back here when you want the full picture.

## What you'll find here

| Page | What it covers |
|------|---------------|
| [The Multi-Agent Landscape](enterprise-landscape.md) | The problem OAM solves, the gap in the current ecosystem |
| [OAM and MCP](oam-and-mcp.md) | How OAM complements MCP for enterprise-scale tool discovery |
| [OAM and A2A](oam-and-a2a.md) | How OAM contracts map to Google's A2A Agent Cards |
| [Technology Stack](technology.md) | Why NATS, why Pydantic, and the service mesh analogy |

```python
from openagentmesh import AgentMesh

# This is all it takes to join a mesh
mesh = AgentMesh("nats://mesh.company.com:4222")

# Discover what's available
catalog = await mesh.catalog()
```

The same code works whether you're running locally or across a multi-region cluster. The only thing that changes is the connection string.
