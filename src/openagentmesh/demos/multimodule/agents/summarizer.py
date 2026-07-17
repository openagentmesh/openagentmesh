"""Summarizer agent: registers on the shared mesh at import time."""

from pydantic import BaseModel

from openagentmesh import AgentSpec

from ..mesh import mesh


class SummarizeInput(BaseModel):
    text: str
    max_length: int = 200


class SummarizeOutput(BaseModel):
    summary: str


@mesh.agent(AgentSpec(
    name="nlp.summarizer",
    description="Summarizes text to a target length. Input: raw text and optional max_length.",
))
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    return SummarizeOutput(summary=req.text[: req.max_length])
