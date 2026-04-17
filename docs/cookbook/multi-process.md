# Multi-Process Agents

The most common deployment: one process provides an agent, another discovers and calls it. No shared imports, no shared memory. Just NATS.

## Provider

**provider.py** registers a summarizer agent and blocks:

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

class SummarizeInput(BaseModel):
    text: str
    max_length: int = 200

class SummarizeOutput(BaseModel):
    summary: str

spec = AgentSpec(
    name="summarizer",
    channel="nlp",
    description="Summarizes text to a target length. Input: raw text and optional max_length. Not for structured data extraction.",
)

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    # Your logic here -- call an LLM, run extractive summarization, anything.
    truncated = req.text[: req.max_length]
    return SummarizeOutput(summary=truncated)

mesh.run()  # blocks, like uvicorn.run()
```

## Consumer

**consumer.py** discovers agents on the mesh and calls one:

```python
import asyncio
from openagentmesh import AgentMesh

async def main():
    mesh = AgentMesh()
    async with mesh:
        # Browse the mesh
        catalog = await mesh.catalog()
        for entry in catalog:
            print(f"{entry.name} - {entry.description}")

        # Call by name
        result = await mesh.call(
            "summarizer",
            {"text": "AgentMesh connects agents over NATS. Agents register, discover, and invoke each other at runtime.", "max_length": 40},
        )
        print(result["summary"])

asyncio.run(main())
```

## Run It

Start NATS, then the provider and consumer in separate terminals:

```bash
# Terminal 1
oam mesh up

# Terminal 2
python provider.py

# Terminal 3
python consumer.py
```

Output:

```
summarizer - Summarizes text to a target length. Input: raw text and optional max_length. Not for structured data extraction.
AgentMesh connects agents over NATS. Ag
```

## How It Works

Both processes connect to the NATS server started by `oam mesh up`. The provider registers its contract (name, schema, description) in the mesh registry. The consumer reads the catalog and invokes the agent by name. No import of the provider's code required.

```mermaid
sequenceDiagram
    participant Provider as provider.py
    participant NATS
    participant Consumer as consumer.py

    Provider->>NATS: Register "summarizer" contract
    Provider->>NATS: Subscribe to mesh.agent.nlp.summarizer

    Consumer->>NATS: mesh.catalog()
    NATS-->>Consumer: [CatalogEntry(name="summarizer", ...)]

    Consumer->>NATS: mesh.call("summarizer", payload)
    NATS->>Provider: Deliver request
    Provider->>NATS: Return SummarizeOutput
    NATS-->>Consumer: {"summary": "..."}
```

## Moving to Shared NATS

Replace the default connection with a connection string in both files. Nothing else changes.

```python
mesh = AgentMesh("nats://mesh.company.com:4222")
```

`AgentMesh()` connects to `nats://localhost:4222` by default. In production, pass the connection string for your shared NATS cluster.
