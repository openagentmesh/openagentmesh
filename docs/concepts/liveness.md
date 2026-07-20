# Liveness

A mesh is only as trustworthy as its catalog. If an agent crashes and the
catalog keeps advertising it for 30 seconds, every caller in that window
wastes an LLM tool-selection cycle, a timeout, and a retry. OpenAgentMesh
detects agents leaving the mesh — by crash, partition, or clean exit — and
reacts in well under a second for the common cases.

## How agents leave, and how the mesh notices

| Mode | Detection | Latency |
|------|-----------|---------|
| Graceful shutdown | Self-deregistration on context exit | Instant |
| Process crash (OOM, SIGKILL) | NATS disconnect advisory (TCP close) | Sub-second |
| Network partition | Disconnect advisory (ping timeout) | 10–20s |
| Zombie (alive but stuck) | Caller timeout | Request timeout |

The fast paths ride on NATS **system events**: when a client's TCP connection
drops, the server emits a `$SYS.ACCOUNT.*.DISCONNECT` advisory immediately.
The mesh **health monitor** subscribes to these advisories, works out which
agents the dead host was serving, removes them from the catalog and registry,
and publishes a **death notice**.

## Death notices

Every departure — detected or self-announced — publishes a JSON notice on:

```
mesh.death.{name}      # e.g. mesh.death.nlp.summarizer
mesh.death.>           # wildcard: every death on the mesh
mesh.death.nlp.>       # every death in the nlp channel
```

```python
async with AgentMesh() as mesh:
    async for notice in mesh.subscribe(subject="mesh.death.>"):
        print(f"{notice['agent']} left the mesh: {notice['reason']}")
        # orchestrators reroute, spawners respawn, dashboards alert
```

The payload:

```json
{
  "agent": "nlp.summarizer",
  "reason": "disconnect",
  "detected_at": "2026-07-18T00:27:27.947596+00:00",
  "instance_id": "f960ad7e68904981b32b041775c01a0e"
}
```

`reason` is `"disconnect"` when the health monitor detected a dropped
connection, `"graceful_shutdown"` when the agent's host deregistered itself.
The `DeathNotice` model (exported from `openagentmesh`) parses the payload
into a typed object: `DeathNotice.model_validate(notice)`.

**Replicas don't produce false alarms.** When an agent runs as multiple
queue-group instances, scaling one replica down (or losing it) is not a
death: the notice fires only when the *last* instance serving that agent
disconnects, and the catalog entry stays put while any replica survives.

## Fast-failing in-flight requests

`no responders` on a subject nobody serves surfaces instantly as `NotFound`.
The harder case is an agent that dies *after* accepting your request — NATS
cannot know your reply will never come, so without liveness machinery you
wait out the full timeout.

Instead, `mesh.call()` and `mesh.stream()` race every request against the
target's death notices. If one arrives before the reply, the call raises
`AgentDied` immediately:

```python
try:
    result = await mesh.call("summarizer", payload, timeout=30.0)
except MeshError as e:
    if e.code == "agent_died":
        print(f"Fast-fail: {e.message}")   # sub-second, not 30s
    elif e.code == "timeout":
        print(f"Slow-fail: {e.message}")   # agent alive but unresponsive
```

`AgentDied.details` carries the death notice. For streams, the death listener
stays active until the end-of-stream marker, so a mid-stream crash raises
from the generator instead of stalling it.

One honest caveat: for a *replicated* agent, the notice only fires when the
last instance goes. If the specific replica processing your request dies
while others live, that request still ends in a timeout — the mesh cannot
yet tell which instance held it.

## What runs the monitor

The monitor belongs to whoever owns the mesh lifecycle — not to every SDK
client (`$SYS` access is privileged, and N monitors would race each other):

- **`AgentMesh.local()`** runs one in-process automatically. Tests and demos
  get full liveness semantics for free.
- **`oam mesh up`** starts one as a companion process and `oam mesh down`
  stops it.
- **Secured meshes** run it explicitly, with a system-account credential for
  advisories and a worker credential for cleanup:

  ```bash
  oam mesh monitor --url nats://mesh:4222 \
      --sys-creds monitor-sys.creds --creds worker.creds
  ```

If no monitor is running, nothing breaks — callers simply fall back to
timeouts, exactly the pre-liveness behavior.

## Under the hood

- Each SDK connection names itself `oam-host-{instance_id}`, and each host
  records the agents it serves in the `mesh-instances` KV bucket. That is
  how a disconnect advisory (which carries only the connection name) maps
  back to catalog entries.
- The dev server configs written by `oam mesh up` and the embedded server
  tune `ping_interval` to 10s (NATS defaults to 2 minutes), which is what
  bounds partition detection at ~20s.
- Zombie detection (heartbeats) is specified in ADR-0016 but not yet built:
  a hung-but-connected agent today looks healthy until callers time out.
