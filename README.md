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

class Input(BaseModel):
    content: str

class Summary(BaseModel):
    text: str

async def main():
    async with AgentMesh.local() as mesh:

        spec = AgentSpec(name="summarizer", channel="nlp",
                         description="Summarizes text to a target length.")

        @mesh.agent(spec)
        async def summarize(req: Input) -> Summary:
            return Summary(text=req.content[:100] + "...")

        result = await mesh.call("summarizer", {"content": "A long document..."})
        print(result)  # {"text": "A long document..."}

asyncio.run(main())
```

One agent, one embedded mesh, no config. For real deployments, run `oam mesh up` and use `AgentMesh()` with `mesh.run()`.

## Documentation

[See the full docs here](https://openagentmesh.github.io/openagentmesh/) (or run `uv run zensical serve` locally).
