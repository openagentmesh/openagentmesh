# Securing the Mesh

A local mesh is open by design: `AgentMesh.local()` and `oam mesh up` start a
NATS server with no credentials, and Hello World stays a five-line program.
The moment a mesh is reachable beyond your machine, that stops being
acceptable — the mesh URL is not a secret, and anyone who can reach an open
mesh can do anything on it.

OAM adopts NATS-native security rather than inventing its own: **NKey + JWT
(decentralized auth)** for identity, optional **mTLS** for transport. There is
no OAM token format, no issuer service, and no lock-in — credentials are
standard NATS `.creds` files that work with any NATS tooling.

## Connecting with credentials

```python
from openagentmesh import AgentMesh

mesh = AgentMesh(
    url="nats://mesh.company.com:4222",
    creds="./risk-pipeline.creds",
)
```

Credentials resolve in this order:

1. The explicit `creds=` argument.
2. The `OAM_CREDS` environment variable.
3. The `creds` field in `.oam-url` (see below).
4. Nothing: connect open. If the server requires auth, the SDK raises
   `ConnectionDenied` immediately, telling you no credentials were presented.

`AgentMesh.local()` never picks up ambient credentials — local development
stays open and zero-ceremony.

For mTLS, pass `tls_cert=`, `tls_key=`, and `tls_ca=` alongside `creds=`.
They are orthogonal: `creds=` is who you are, TLS is how the bytes travel.

## The `.oam-url` file

`oam mesh connect` records where subsequent `oam` commands (and SDK processes
run from that directory) should connect. With credentials it writes a small
TOML instead of the bare URL:

```bash
oam mesh connect nats://mesh.company.com:4222 --creds ./luca.creds
```

```toml
url = "nats://mesh.company.com:4222"
creds = "./luca.creds"
```

A bare-URL `.oam-url` from older versions keeps working. Relative `creds`
paths resolve against the file's own directory. `oam auth whoami` shows which
identity would be used right now.

## Bootstrapping credentials: `oam auth`

`oam auth init` wraps [nsc](https://github.com/nats-io/nsc), the NATS
credentials CLI, and produces everything a secured mesh needs in one step —
an operator, a system account (required for JetStream in JWT mode), an
application account with JetStream enabled, and a ready-to-run server config:

```bash
oam auth init --name mymesh
nats-server -c .oam/server.conf

oam auth user add risk-pipeline --role worker
oam auth user add dashboard --role observer
```

Users are minted from three coarse role templates:

| Role | Can | Cannot |
|------|-----|--------|
| `worker` | host agents, invoke, read/write shared state | touch `$SYS.>` |
| `invoker` | call agents, read the catalog, subscribe to events | host agents, write shared state |
| `observer` | read the catalog, watch events/errors/health | invoke or publish anything on `mesh.>` |

Roles are process-level and deliberately coarse: a process hosting several
agents holds one `worker` credential, and one connection is one identity.

To revoke a user:

```bash
oam auth user revoke risk-pipeline
# regenerated .oam/server.conf — reload or restart the server to apply
```

## What denial looks like

Every NATS-level rejection surfaces as `ConnectionDenied` (wire code
`connection_denied`), a `MeshError` subclass:

- Connecting without (or with invalid) credentials against a secured server
  raises it from `async with mesh:`, naming the credentials that were used.
- Calling an agent your role may not invoke raises it from `mesh.call()` —
  the server reports permission violations asynchronously, and the SDK
  correlates them back to the blocked call instead of letting it read as a
  timeout.

```python
from openagentmesh import AgentMesh, ConnectionDenied

try:
    async with AgentMesh(url=url, creds="./viewer.creds") as mesh:
        await mesh.call("scorer", {"trade_id": "t-17"})
except ConnectionDenied as e:
    print(e.code)      # "connection_denied"
    print(e.message)   # names the denied subject / missing permission
```

See the [secured mesh cookbook recipe](../cookbook/secured-mesh.md) for the
full walkthrough, end to end.
