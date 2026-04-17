# Quickstart

Two agents discovering and calling each other in under 30 lines.

## Installation

```bash
pip install openagentmesh
```

## Prerequisites

Start a local development server in a separate terminal:

```bash
oam mesh up
```

## Hello World

One file. Two agents. One calls the other.

```python
import asyncio
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()  # connects to localhost:4222

class EchoInput(BaseModel):
    message: str

class EchoOutput(BaseModel):
    reply: str

spec = AgentSpec(name="echo", description="Echoes a message back.")

@mesh.agent(spec)
async def echo(req: EchoInput) -> EchoOutput:
    return EchoOutput(reply=f"Echo: {req.message}")

async def main():
    async with mesh:
        result = await mesh.call("echo", {"message": "hello"})
        print(result["reply"])  # Echo: hello

asyncio.run(main())
```

!!! info "What just happened?"
    `oam mesh up` started a local development server with JetStream and KV buckets. The `@mesh.agent` decorator registered `echo` with a typed contract. `mesh.call()` discovered and invoked it, all through the message bus, not a direct function call.

## Two Separate Processes

The more realistic case: provider and consumer run independently.

**provider.py.** Registers the agent and keeps it running:

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
    description="Summarizes text to a target length. Input: raw text. Not for structured data.",
)

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    # Use any LLM framework, any model, any logic here.
    truncated = req.text[: req.max_length]
    return SummarizeOutput(summary=truncated)

mesh.run()  # blocks, like uvicorn.run()
```

**consumer.py.** Discovers the agent and calls it:

```python
import asyncio
from openagentmesh import AgentMesh

async def main():
    mesh = AgentMesh()
    async with mesh:
        # See what's on the mesh
        catalog = await mesh.catalog()
        for entry in catalog:
            print(entry.name, "-", entry.description)

        # Call by name
        result = await mesh.call(
            "summarizer",
            {"text": "AgentMesh is a protocol for agent-to-agent communication.", "max_length": 50},
        )
        print(result["summary"])

asyncio.run(main())
```

Run the provider first, then the consumer:

```bash
python provider.py &
python consumer.py
```

## Channels

Channels are namespace prefixes that group agents by domain or team.

```python
spec = AgentSpec(
    name="scorer",
    channel="finance.risk",
    description="Scores credit risk from a company profile.",
)

@mesh.agent(spec)
async def score(req: ScoreInput) -> ScoreOutput:
    ...
```

Discover all agents in a channel:

```python
agents = await mesh.catalog(channel="finance.risk")
```

Agents without a channel register at the root level and are invoked directly by name.

## Connect to Shared NATS

Replace the default localhost connection with a connection string. Agent code is unchanged.

```python
mesh = AgentMesh("nats://mesh.company.com:4222")
```

> **Note:** `AgentMesh()` connects to `nats://localhost:4222` by default (your `oam mesh up` server). In staging and production, pass the connection string for your shared NATS deployment.

## Embed in an Existing App

Use `async with mesh:` instead of `mesh.run()` to embed the mesh in an existing async application.

```python
async def lifespan(app):
    async with mesh:
        yield
```

## Async Callback Invocation

For fire-and-forget invocations, use `mesh.send()` with a reply subject.

```python
import uuid

request_id = uuid.uuid4().hex
await mesh.send(
    "summarizer",
    {"text": long_doc, "max_length": 500},
    reply_to=f"mesh.results.{request_id}",
)
# The agent processes the request; result arrives on mesh.results.{request_id}
```

## LLM Tool Definitions

Fetch an agent's full contract and use its schemas for LLM tool injection.

```python
contract = await mesh.contract("summarizer")

# Access schemas directly
contract.input_schema    # JSON Schema dict for the input model
contract.output_schema   # JSON Schema dict for the output model
contract.description     # LLM-consumable description
```

Build tool definitions for your LLM provider:

```python
# Example: construct an Anthropic tool definition
tool = {
    "name": contract.name,
    "description": contract.description,
    "input_schema": contract.input_schema,
}
```

## Reference

### AgentMesh

| Method | Description |
|--------|-------------|
| `AgentMesh(url)` | Connect to an existing NATS server |
| `AgentMesh()` | Connect to localhost:4222 (default) |
| `async with AgentMesh.local() as mesh:` | Embedded NATS for tests and demos |
| `mesh.run()` | Start event loop, block until interrupted |
| `async with mesh:` | Connect, subscribe agents, and serve. Disconnects on exit. |

### Registration

| Method | Description |
|--------|-------------|
| `@mesh.agent(spec)` | Register an async function as a mesh agent. `spec` is an `AgentSpec` instance. |

### Invocation

| Method | Description |
|--------|-------------|
| `await mesh.call(name, payload, timeout=30.0)` | Synchronous request/reply. Returns `dict`. |
| `async for chunk in mesh.stream(name, payload)` | Streaming request. Yields `dict` chunks. |
| `await mesh.send(name, payload, reply_to)` | Async callback, non-blocking |

### Discovery

| Method | Description |
|--------|-------------|
| `await mesh.catalog(channel=None, tags=None)` | Returns `list[CatalogEntry]` (name, description, version, tags, invocable, streaming) |
| `await mesh.discover(channel=None)` | Full `AgentContract` objects |
| `await mesh.contract(name)` | Single agent's full contract (authoritative) |

### AgentSpec

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | required | Agent name |
| `description` | `str` | required | LLM-consumable description |
| `channel` | `str \| None` | `None` | Namespace prefix |
| `tags` | `list[str]` | `[]` | Searchable tags |
| `version` | `str` | `"0.1.0"` | Semver version |

### CLI

| Command | Description |
|---------|-------------|
| `oam mesh up` | Start local development server with JetStream and pre-created KV buckets |
| `oam mesh catalog` | List registered agents |
