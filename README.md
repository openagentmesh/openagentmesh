# OpenAgentMesh

> Connect agents like you'd call an API

OpenAgentMesh is the fabric for multi-agent systems. It makes coding complex interaction patterns as simple as writing REST endpoints.

It's an SDK with batteries included:

- Request/reply, pub/sub, and event streaming
- Typed contracts with self-discovery
- Shared KV and Object stores

No hardcoded interactions, full decoupling.

## Quickstart

**1. Start the mesh:**

```bash
oam mesh up
```

**2. Register an agent** (`agent.py`):

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

class EchoInput(BaseModel):
    message: str

class EchoOutput(BaseModel):
    reply: str

@mesh.agent(AgentSpec(name="echo", description="Echoes a message back."))
async def echo(req: EchoInput) -> EchoOutput:
    return EchoOutput(reply=f"Echo: {req.message}")

mesh.run()
```

```bash
python agent.py
```

**3. Discover and call it from the terminal:**

```bash
oam mesh catalog
oam agent contract echo
oam agent call echo '{"message": "hello"}'
```

No hardcoded addresses. The CLI discovers `echo` from the mesh, reads its contract, and calls it.

## Documentation

[See the full docs here](https://openagentmesh.github.io/openagentmesh/) (or run `uv run zensical serve` locally).
