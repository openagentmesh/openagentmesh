# A Secured Multi-Node Mesh

Take a mesh from "open on localhost" to "credentialed, least-privilege,
multi-process" with one init command and a role template per participant.
This recipe bootstraps a JWT-secured NATS server, then runs three differently
privileged processes against it: a worker that hosts an agent, an invoker
that calls it, and an observer that can watch but not touch.

## Bootstrap the credential tree

```bash
oam auth init --name mymesh
```

This creates `.oam/` containing an isolated [nsc](https://github.com/nats-io/nsc)
store (operator + system account + JetStream-enabled application account) and
a ready-to-run `server.conf` with a memory resolver. Start the server:

```bash
nats-server -c .oam/server.conf
```

Mint one credential per process, by role:

```bash
oam auth user add pipeline --role worker    # hosts agents
oam auth user add caller   --role invoker   # calls agents
oam auth user add viewer   --role observer  # read-only
```

Each command writes a standard NATS `./<name>.creds` file (mode 0600).

## The worker: hosts an agent

```python
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


class ScoreRequest(BaseModel):
    trade_id: str


class ScoreReply(BaseModel):
    risk: float


mesh = AgentMesh(url="nats://mesh.internal:4222", creds="./pipeline.creds")


@mesh.agent(AgentSpec(name="scorer", description="Scores risk for trades."))
async def scorer(req: ScoreRequest) -> ScoreReply:
    return ScoreReply(risk=0.17 if req.trade_id else 1.0)


mesh.run()
```

Nothing about the agent changes — auth is one constructor argument. The
worker role covers everything an agent process does: serving invocations,
publishing its contract, catalog updates, events, shared state.

## The invoker: calls across processes

```python
from openagentmesh import AgentMesh

async def main():
    mesh = AgentMesh(url="nats://mesh.internal:4222", creds="./caller.creds")
    async with mesh:
        result = await mesh.call("scorer", {"trade_id": "t-17"})
        print(result["risk"])
```

## The observer: watch, but don't touch

```python
from openagentmesh import AgentMesh, ConnectionDenied

async def main():
    mesh = AgentMesh(url="nats://mesh.internal:4222", creds="./viewer.creds")
    async with mesh:
        # Reading the catalog works: observers may discover.
        for entry in await mesh.catalog():
            print(entry.name, "-", entry.description)

        # Invoking does not: the server denies the publish, and the SDK
        # surfaces it as ConnectionDenied rather than a timeout.
        try:
            await mesh.call("scorer", {"trade_id": "t-17"}, timeout=2.0)
        except ConnectionDenied as e:
            print("denied, as designed:", e.message)
```

## Locking someone out

```bash
oam auth user revoke pipeline
# regenerated .oam/server.conf — reload/restart the server to apply
```

After the server reloads, `pipeline.creds` is rejected at connect time
(`ConnectionDenied` from `async with mesh:`); every other credential keeps
working.

## Notes

- **No credentials?** Against this server, an `AgentMesh(url=...)` with no
  creds raises `ConnectionDenied` immediately, telling you the server
  requires auth and where credentials can come from (`creds=`, `OAM_CREDS`,
  or `.oam-url`).
- **Where the creds come from** is standard nsc material — the `.oam/` store
  works with plain `nsc` commands if you outgrow the role templates.
- **Roles are process-level.** One connection is one identity; a process
  hosting five agents holds one worker credential. Finer-grained, per-agent
  policy is a logical-layer concern (see the concepts page).

Full background: [Securing the Mesh](../concepts/security.md).
