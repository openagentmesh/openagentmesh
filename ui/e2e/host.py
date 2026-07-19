"""Agent host for the admin-UI smoke e2e (ui/e2e/smoke.mjs).

Registers a Responder against the mesh named by OAM_URL, then self-calls it
once a second so the event feed has real ``mesh.agent.*`` traffic to show.
Prints ``E2E-HOST-READY`` once the first self-call round-trip succeeds
(registration is flushed and the agent is invocable at that point).
"""

import asyncio
import os

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


class EchoInput(BaseModel):
    text: str


class EchoOutput(BaseModel):
    echoed: str


async def main() -> None:
    mesh = AgentMesh(url=os.environ["OAM_URL"])

    @mesh.agent(AgentSpec(name="echo", description="Echoes the text it is given."))
    async def echo(req: EchoInput) -> EchoOutput:
        return EchoOutput(echoed=req.text)

    async with mesh:
        ready = False
        while True:
            await mesh.call("echo", {"text": "tick"})
            if not ready:
                print("E2E-HOST-READY", flush=True)
                ready = True
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
