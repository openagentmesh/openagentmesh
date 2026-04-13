# Quickstart

Two agents discovering and calling each other in under 30 lines.

## Installation

```bash
pip install agentmesh
```

## Hello World

One file. Two agents. One calls the other.

```python
import asyncio
from pydantic import BaseModel
from openagentmesh import AgentMesh

mesh = AgentMesh.local()  # starts embedded NATS, no setup required

class EchoInput(BaseModel):
    message: str

class EchoOutput(BaseModel):
    reply: str

@mesh.agent(name="echo", description="Echoes a message back.")
async def echo(req: EchoInput) -> EchoOutput:
    return EchoOutput(reply=f"Echo: {req.message}")

async def main():
    await mesh.start()
    result = await mesh.call("echo", {"message": "hello"})
    print(result["reply"])  # Echo: hello
    await mesh.stop()

asyncio.run(main())
```

!!! info "What just happened?"
    `AgentMesh.local()` started an embedded NATS server. The `@mesh.agent` decorator registered `echo` with a typed contract. `mesh.call()` discovered and invoked it — all through the message bus, not a direct function call.

## Two Separate Processes

The more realistic case: provider and consumer run independently.

**provider.py** — registers the agent and keeps it running:

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh

mesh = AgentMesh.local()

class SummarizeInput(BaseModel):
    text: str
    max_length: int = 200

class SummarizeOutput(BaseModel):
    summary: str

@mesh.agent(
    name="summarizer",
    channel="nlp",
    description="Summarizes text to a target length. Input: raw text. Not for structured data.",
)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    # Use any LLM framework, any model, any logic here.
    truncated = req.text[: req.max_length]
    return SummarizeOutput(summary=truncated)

mesh.run()  # blocks, like uvicorn.run()
```

**consumer.py** — discovers the agent and calls it:

```python
import asyncio
from openagentmesh import AgentMesh

async def main():
    mesh = AgentMesh.local()
    await mesh.start()

    # See what's on the mesh
    catalog = await mesh.catalog()
    for entry in catalog:
        print(entry["name"], "-", entry["description"])

    # Call by name
    result = await mesh.call(
        "summarizer",
        {"text": "AgentMesh is a protocol for agent-to-agent communication.", "max_length": 50},
    )
    print(result["summary"])

    await mesh.stop()

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
@mesh.agent(name="scorer", channel="finance.risk",
            description="Scores credit risk from a company profile.")
async def score(req: ScoreInput) -> ScoreOutput:
    ...
```

Discover all agents in a channel:

```python
agents = await mesh.catalog(channel="finance.risk")
```

Agents without a channel register at the root level and are invoked directly by name.

## Connect to Shared NATS

Replace `AgentMesh.local()` with a connection string. Agent code is unchanged.

```python
mesh = AgentMesh("nats://mesh.company.com:4222")
```

> **Note:** `AgentMesh.local()` is for development only. It starts an embedded NATS subprocess. In staging and production, connect to a shared NATS deployment.

## Embed in an Existing App

Use `await mesh.start()` / `await mesh.stop()` instead of `mesh.run()` to embed the mesh in an existing async application.

```python
async def lifespan(app):
    await mesh.start()
    yield
    await mesh.stop()
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

Convert any agent contract to an LLM-ready tool definition.

```python
contract = await mesh.contract("summarizer")

contract.to_openai_tool()      # OpenAI function calling format
contract.to_anthropic_tool()   # Anthropic tool use format
contract.to_generic_tool()     # Generic JSON Schema format
contract.to_agent_card()       # A2A Agent Card format
```

Pass `url=` to `to_agent_card()` when exposing the agent at a federation boundary:

```python
contract.to_agent_card(url="https://api.company.com/agents/summarizer")
```

## Reference

### AgentMesh

| Method | Description |
|--------|-------------|
| `AgentMesh(url)` | Connect to an existing NATS server |
| `AgentMesh.local()` | Start embedded NATS subprocess (dev only) |
| `mesh.run()` | Start event loop, block until interrupted |
| `await mesh.start()` | Start non-blocking (for embedding) |
| `await mesh.stop()` | Graceful shutdown: drain → deregister → disconnect |

### Registration

| Method | Description |
|--------|-------------|
| `@mesh.agent(name, description, channel=None, tags=[])` | Register an async function as a mesh agent |
| `mesh.register(name, description, handler, input_model, output_model, channel=None)` | Imperative registration |

### Invocation

| Method | Description |
|--------|-------------|
| `await mesh.call(name, payload, timeout=30.0)` | Synchronous request/reply |
| `await mesh.send(name, payload, reply_to)` | Async callback, non-blocking |

### Discovery

| Method | Description |
|--------|-------------|
| `await mesh.catalog(channel=None, tags=None)` | Lightweight listing (name, description, version, tags) |
| `await mesh.discover(channel=None)` | Full `AgentContract` objects |
| `await mesh.contract(name)` | Single agent's full contract (authoritative) |

### AgentContract

| Method | Description |
|--------|-------------|
| `.to_openai_tool()` | OpenAI function calling format |
| `.to_anthropic_tool()` | Anthropic tool use format |
| `.to_generic_tool()` | Generic JSON Schema format |
| `.to_agent_card(url=None)` | A2A Agent Card format |

### CLI

| Command | Description |
|---------|-------------|
| `agentmesh up` | Start local NATS with JetStream and pre-created KV buckets |
| `agentmesh status` | Show registered agents and health |
