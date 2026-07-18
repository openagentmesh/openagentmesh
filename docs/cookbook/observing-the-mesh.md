# Observing the Mesh

Something in production is slow and you don't know what. This recipe walks a
live debugging session: tail the mesh's own log stream, turn one agent up to
`debug` without restarting anything, find the problem, turn it back down.
The machinery is explained in [Observability](../concepts/observability.md).

## Watch failures as they happen

By default every agent publishes `warn`-level events — failures and
validation errors — to `mesh.logs.{name}`. A monitor is just a subscriber:

```python
from openagentmesh import AgentMesh


async def failure_monitor(mesh: AgentMesh):
    """Alert on any failure, anywhere on the mesh."""
    async for event in mesh.observe.logs(level="warn"):
        print(f"{event.agent}: {event.event} — {event.message}")
        # request_failed carries the taxonomy code:
        if event.data.get("code") == "handler_error":
            ...  # page someone, count it, open an issue
```

The same stream from a terminal:

```bash
oam observe logs --level warn
```

## Turn one agent up to debug

Request-level events (`request_received`, `request_completed` with
`duration_ms`) are `debug` and silent by default. Flip the suspect agent —
the change applies live, no restart:

```python
await mesh.observe.set("nlp.summarizer", log_level="debug")

async for event in mesh.observe.logs("nlp.summarizer"):
    if event.event == "request_completed":
        print(f"{event.request_id}: {event.data['duration_ms']}ms")
```

Watch the durations, find the slow path, then put it back:

```python
await mesh.observe.set("nlp.summarizer", log_level="info")
```

Or do the whole thing from the CLI:

```bash
oam observe set nlp.summarizer --log-level debug
oam observe logs nlp.summarizer
oam observe set nlp.summarizer --log-level info
```

## Check what's in effect

Config is two-tier — per-agent overrides a mesh-wide `global` default — and
`get()` tells you which tier answered:

```python
config = await mesh.observe.get("nlp.summarizer")
print(config.log_level, config.source)   # "debug", "agent"

config = await mesh.observe.get("nlp.classifier")
print(config.log_level, config.source)   # "info", "default"
```

`oam observe config` prints the same picture for the whole mesh.

## Try it

Run `oam mesh up`, start any agent from the quickstart, and in a second
terminal run `oam observe logs --level debug` while you
`oam observe set <agent> --log-level debug`. Invoke the agent and watch the
request pairs stream by with their durations.
