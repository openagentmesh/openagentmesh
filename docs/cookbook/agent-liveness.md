# Surviving Agent Failures

Agents die: OOM kills, crashed containers, unplugged laptops. This recipe
shows the two halves of living with that — callers that fail over instead of
stalling, and a watchdog that reacts the moment anything leaves the mesh.
The machinery behind it is explained in
[Liveness](../concepts/liveness.md).

## Fail over on death, instantly

`mesh.call()` races every request against death notices for its target. When
the agent dies mid-request you get `AgentDied` in well under a second — not a
30-second timeout — which makes failover cheap:

```python
from openagentmesh import AgentDied, AgentMesh, NotFound


async def call_resilient(mesh: AgentMesh, primary: str, fallback: str, payload):
    """Try the primary agent; fail over the moment it leaves the mesh."""
    try:
        return await mesh.call(primary, payload, timeout=30.0)
    except (AgentDied, NotFound):
        # AgentDied: it died while holding our request (sub-second signal).
        # NotFound: it was already gone before we called.
        return await mesh.call(fallback, payload, timeout=30.0)
```

`AgentDied` and `NotFound` are the two faces of the same fact — the agent is
gone — distinguished by whether your request was already in flight. Neither
means your *input* was bad, so sending the same payload to a replacement is
safe.

## Watch the whole mesh

Death notices are plain subjects, so a supervisor is just a subscriber:

```python
async def watchdog(mesh: AgentMesh):
    """React to any agent leaving the mesh, however it left."""
    async for notice in mesh.subscribe(subject="mesh.death.>"):
        if notice["reason"] == "disconnect":
            # Crash or partition: the host never said goodbye.
            print(f"LOST {notice['agent']} — respawn or page someone")
        else:  # "graceful_shutdown"
            print(f"{notice['agent']} deregistered cleanly")
```

Scope the wildcard to a channel (`mesh.death.nlp.>`) to supervise one team
of agents. Replicated agents only produce a notice when their *last*
instance goes, so scale-downs and rolling restarts stay quiet.

## Try it

Run a mesh with `oam mesh up` (it starts the health monitor for you), start
any agent from the quickstart, and `kill -9` its process. The watchdog
prints the loss, `oam mesh catalog` no longer lists the agent, and in-flight
calls surface `agent_died` immediately.
