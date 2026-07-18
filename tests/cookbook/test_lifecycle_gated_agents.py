"""Executable twin of docs/cookbook/lifecycle-gated-agents.md (ADR-0055)."""

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


class TestLifecycleGatedAgentsRecipe:
    async def test_main_completes(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)

    async def test_report_queued_while_gate_closed(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)
            queued = await mesh.kv.get("queued.ridge-7")
            assert SmokeReport.model_validate_json(queued).location == "ridge-7"
