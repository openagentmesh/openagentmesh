# OpenAgentMesh

> Connect agents like you'd call an API

OpenAgentMesh is the fabric for multi-agent systems. It makes coding complex interaction patterns as simple as writing REST endpoints.

It's an SDK with batteries included:

- Request/reply, pub/sub, and event streaming
- Typed contracts with self-discovery
- Shared KV and Object stores

No hardcoded interactions, full decoupling.

## Quickstart

```python
import asyncio
from openagentmesh import AgentMesh, AgentSpec
from pydantic import BaseModel

class Summary(BaseModel):
    text: str

async def main():
    async with AgentMesh.local() as mesh:

        spec = AgentSpec(name="summarizer", channel="nlp",
                         description="Summarizes text to a target length.")

        @mesh.agent(spec)
        async def summarize(req: dict) -> Summary:
            return Summary(text=req["content"][:100] + "...")

        await mesh.start()
        result = await mesh.call("summarizer", {"content": "A long document..."})

asyncio.run(main())
```

Two agents. One embedded mesh server. No imports between them, no HTTP servers, no shared packages.

## Documentation

Full docs at [openagentmesh.dev](https://openagentmesh.dev) (or run `uv run zensical serve` locally).
