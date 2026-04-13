# Agents

An agent is an async function registered on the mesh. It receives typed input, does work, and returns typed output.

## Registering an Agent

Use the `@mesh.agent` decorator:

```python
from pydantic import BaseModel
from agentmesh import AgentMesh

mesh = AgentMesh.local()

class EchoInput(BaseModel):
    message: str

class EchoOutput(BaseModel):
    reply: str

@mesh.agent(name="echo", description="Echoes a message back.")
async def echo(req: EchoInput) -> EchoOutput:
    return EchoOutput(reply=f"Echo: {req.message}")
```

The decorator:

1. Subscribes to a NATS queue group at `mesh.agent.{channel}.{name}`
2. Deserializes and validates input via Pydantic v2
3. Calls your handler function
4. Serializes the response
5. Writes the contract to the registry on startup

## Imperative Registration

For cases where decorators don't fit:

```python
mesh.register(
    name="echo",
    description="Echoes a message back.",
    handler=echo_handler,
    input_model=EchoInput,
    output_model=EchoOutput,
)
```

## Lifecycle

Agents follow a predictable lifecycle:

1. **Start** — `mesh.run()` (blocking) or `await mesh.start()` (non-blocking)
2. **Register** — subscribe to NATS subject, write contract to KV
3. **Serve** — handle incoming requests via queue group
4. **Stop** — `await mesh.stop()`: unsubscribe, drain, deregister, disconnect

## Queue Groups

Every agent subscribes via a NATS queue group. This means multiple instances of the same agent automatically load-balance with no configuration changes. Deploy three replicas of `summarizer` and NATS distributes requests across them.
