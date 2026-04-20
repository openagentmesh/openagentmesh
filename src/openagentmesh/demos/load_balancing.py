"""Distribute requests across multiple agent instances via queue groups."""

import asyncio

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


class TranslateInput(BaseModel):
    text: str
    target_language: str = "es"


class TranslateOutput(BaseModel):
    translated: str
    handled_by: str


async def main(mesh: AgentMesh) -> None:
    instance_counter = {"n": 0}

    @mesh.agent(AgentSpec(name="translator", channel="nlp", description="Translates text to a target language."))
    async def translate(req: TranslateInput) -> TranslateOutput:
        instance_counter["n"] += 1
        instance_id = instance_counter["n"]
        await asyncio.sleep(0.05)
        return TranslateOutput(
            translated=f"[{req.target_language}] {req.text}",
            handled_by=f"instance-{instance_id}",
        )

    # Fire 10 concurrent requests
    tasks = [
        mesh.call("translator", TranslateInput(text=f"Hello #{i}", target_language="es"))
        for i in range(10)
    ]
    results = await asyncio.gather(*tasks)

    for i, result in enumerate(results):
        print(f"Request #{i}: handled by {result['handled_by']}")

    # Show distribution
    instances = [r["handled_by"] for r in results]
    print()
    for instance in sorted(set(instances)):
        count = instances.count(instance)
        print(f"  {instance}: {count} requests")
