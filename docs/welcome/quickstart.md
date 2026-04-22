# Quickstart

## Installation

**As a dependency** (projects using OAM agents):

```bash
uv add openagentmesh
# or
pip install openagentmesh
```

**As a CLI tool** (using `oam` commands directly):

```bash
uv tool install openagentmesh
```

**For development:**

```bash
git clone https://github.com/openagentmesh/openagentmesh.git
cd openagentmesh
uv sync
```

## Hello World

Start a local development server:

```bash
oam mesh up
```

Register an agent (`agent.py`):

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()  # connects to localhost:4222

class EchoInput(BaseModel):
    message: str

class EchoOutput(BaseModel):
    reply: str

@mesh.agent(AgentSpec(name="echo", description="Echoes a message back."))
async def echo(req: EchoInput) -> EchoOutput:
    return EchoOutput(reply=f"Echo: {req.message}")

mesh.run()  # blocks, like uvicorn.run()
```

```bash
python agent.py
```

Now discover and call it from the terminal:

```bash
oam mesh catalog                          # list registered agents
oam agent contract echo                   # view the full contract and input schema
oam agent call echo '{"message": "hi"}'  # invoke it
```

!!! info "What just happened?"
    `oam mesh up` started a local development server with JetStream and KV buckets. `@mesh.agent` registered `echo` with a typed contract derived from the function signature. `mesh.run()` connects to the bus, publishes the contract, and serves requests until interrupted. The CLI discovered `echo` from the catalog without knowing its address.

## Agent-to-Agent Calls

The fabric's value shows when agents call each other. One file, two agents: `editor` calls `writer` by name, with no import and no address.

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

class DraftInput(BaseModel):
    topic: str

class DraftOutput(BaseModel):
    text: str

class EditInput(BaseModel):
    topic: str

class EditOutput(BaseModel):
    polished: str

@mesh.agent(AgentSpec(name="writer", description="Drafts text on a given topic."))
async def writer(req: DraftInput) -> DraftOutput:
    return DraftOutput(text=f"A draft about {req.topic}.")

@mesh.agent(AgentSpec(name="editor", description="Polishes a draft by calling writer."))
async def editor(req: EditInput) -> EditOutput:
    draft = await mesh.call("writer", {"topic": req.topic})
    return EditOutput(polished=draft["text"].upper())

mesh.run()
```

```bash
python app.py &
oam agent call editor '{"topic": "meshes"}'
```

`editor` discovers and calls `writer` through the mesh. The same code works whether `writer` runs in the same process or on a different machine.

## Two Separate Processes

The more realistic deployment: each agent runs independently.

**writer.py:**

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

class SummarizeInput(BaseModel):
    text: str
    max_length: int = 200

class SummarizeOutput(BaseModel):
    summary: str

@mesh.agent(AgentSpec(
    name="summarizer",
    channel="nlp",
    description="Summarizes text to a target length. Input: raw text. Not for structured data.",
))
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    return SummarizeOutput(summary=req.text[: req.max_length])

mesh.run()
```

**consumer.py.** Discovers the agent and calls it. `async with mesh:` is the idiom for interacting with the mesh **without registering agents of your own**, scripts, notebooks, and orchestrators that only discover and call.

```python
import asyncio
from openagentmesh import AgentMesh

async def main():
    mesh = AgentMesh()
    async with mesh:
        catalog = await mesh.catalog()
        for entry in catalog:
            print(entry.name, "-", entry.description)

        result = await mesh.call(
            "summarizer",
            {"text": "OpenAgentMesh makes coding multi-agent systems as easy as writing a REST endpoint", "max_length": 50},
        )
        print(result["summary"])

asyncio.run(main())
```

```bash
python writer.py &
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

For non-blocking invocations, use `mesh.send()` with a callback:

```python
from openagentmesh import MeshError

async def on_summary(result: dict):
    print(result["summary"])

async def on_error(err: MeshError):
    print(f"Failed: {err.message}")

await mesh.send(
    "summarizer",
    {"text": long_doc, "max_length": 500},
    on_reply=on_summary,
    on_error=on_error,
    timeout=30.0,
)
# Continues immediately. Callback fires when the agent responds.
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
| `await mesh.send(name, payload, on_reply=cb, on_error=err_cb)` | Managed async callback |
| `await mesh.send(name, payload, reply_to=subject)` | Manual reply subject |
| `await mesh.send(name, payload)` | Fire-and-forget |

### Subscription

| Method | Description |
|--------|-------------|
| `async for msg in mesh.subscribe(agent=name)` | Subscribe to an agent's event stream |
| `async for msg in mesh.subscribe(channel=name)` | Subscribe to all events in a channel (wildcard) |
| `async for msg in mesh.subscribe(subject=raw)` | Subscribe to a raw NATS subject |

### Discovery

| Method | Description |
|--------|-------------|
| `await mesh.catalog(channel=None, tags=None, streaming=None, invocable=None)` | Returns `list[CatalogEntry]` (name, description, version, tags, invocable, streaming) |
| `await mesh.discover(channel=None)` | Full `AgentContract` objects |
| `await mesh.contract(name, channel=None)` | Single agent's full contract (authoritative) |

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
