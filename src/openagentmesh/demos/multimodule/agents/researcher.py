"""Researcher agent: registers on the shared mesh at import time."""

from pydantic import BaseModel

from openagentmesh import AgentSpec

from ..mesh import mesh


class Query(BaseModel):
    topic: str


class ResearchResult(BaseModel):
    findings: str


@mesh.agent(AgentSpec(name="analysts.researcher", description="Researches a topic."))
async def research(req: Query) -> ResearchResult:
    return ResearchResult(findings=f"Research on {req.topic}: ...")
