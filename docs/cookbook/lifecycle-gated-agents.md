# Lifecycle-Gated Agents

An incident-response fleet that only comes online while an incident is
active. The dispatcher declares its own on/off condition with
`active_when`; an always-on intake agent degrades gracefully while the
dispatcher is offline by catching `NotAvailable`.

No controller process starts or stops anything: flipping one KV key gates
every instance of the dispatcher, on every host, at once.

## The Code

```python
import asyncio
import json

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, NotAvailable


class SmokeReport(BaseModel):
    location: str


class Dispatch(BaseModel):
    action: str


def incident_active(v: bytes | None) -> bool:
    return json.loads(v) == "active" if v else False


async def main(mesh: AgentMesh) -> None:
    # Gated: subscribed only while incident.mode is "active".
    @mesh.agent(
        AgentSpec(
            name="fleet.dispatcher",
            description="Dispatches response units during active incidents",
        ),
        active_when=mesh.kv_condition("incident.mode", incident_active),
    )
    async def dispatcher(report: SmokeReport) -> Dispatch:
        return Dispatch(action=f"units to {report.location}")

    # Always on: queues reports while the dispatcher is offline.
    @mesh.agent(
        AgentSpec(
            name="fleet.intake",
            description="Receives smoke reports; queues them when no incident is active",
        )
    )
    async def intake(report: SmokeReport) -> Dispatch:
        try:
            return Dispatch(**await mesh.call("fleet.dispatcher", report))
        except NotAvailable:
            await mesh.kv.put(f"queued.{report.location}", report.model_dump_json())
            return Dispatch(action="queued until incident activates")

    # No incident yet: the dispatcher is in the catalog but offline.
    result = await mesh.call("fleet.intake", {"location": "ridge-7"})
    assert result["action"] == "queued until incident activates"

    # Declare the incident: every dispatcher instance's gate opens.
    await mesh.kv.put("incident.mode", json.dumps("active"))
    while True:  # the gate opens within milliseconds; retry absorbs the propagation
        try:
            result = await mesh.call("fleet.dispatcher", {"location": "ridge-7"})
            break
        except NotAvailable:
            await asyncio.sleep(0.05)
    assert result["action"] == "units to ridge-7"

    # Stand down: the dispatcher drains in-flight work and goes offline.
    await mesh.kv.put("incident.mode", json.dumps("contained"))
```

## Why This Works

- **`active_when` is declarative.** The dispatcher carries its own
  lifecycle rule; nothing else needs to know it exists. Deploy ten
  replicas and the one KV key gates all ten.
- **`NotAvailable` is a distinct, catchable state.** The intake agent
  distinguishes "dispatcher is gated offline, queue for later"
  (`NotAvailable`) from "no such agent" (`NotFound`) — the catalog entry
  survives the gate, which is what makes the distinction possible.
- **Draining is automatic.** Requests in flight when the incident ends
  finish normally (up to the condition's `drain_timeout`, default 30 s);
  only new requests stop arriving.

See [Lifecycle Gates](../concepts/lifecycle.md) for condition semantics,
`subject_condition`, and multi-instance behavior.
