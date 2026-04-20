"""Provider and consumer in one process: register an agent, discover it, call it."""

import asyncio

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


class SummarizeInput(BaseModel):
    text: str
    max_length: int = 200


class SummarizeOutput(BaseModel):
    summary: str


async def main(mesh: AgentMesh) -> None:
    @mesh.agent(AgentSpec(
        name="summarizer",
        channel="nlp",
        description="Summarizes text to a target length. Input: raw text and optional max_length.",
    ))
    async def summarize(req: SummarizeInput) -> SummarizeOutput:
        truncated = req.text[:req.max_length]
        return SummarizeOutput(summary=truncated)

    # Discover agents on the mesh
    catalog = await mesh.catalog()
    for entry in catalog:
        print(f"{entry.name} - {entry.description}")

    # Call by name
    result = await mesh.call(
        "summarizer",
        SummarizeInput(
            text="AgentMesh connects agents over NATS. Agents register, discover, and invoke each other at runtime.",
            max_length=40,
        ),
    )
    print(f"\nResult: {result['summary']}")
