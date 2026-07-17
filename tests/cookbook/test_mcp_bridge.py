"""Executable twin of docs/cookbook/mcp-bridge.md.

Same code as the recipe (agents, flags, export policy), driven by a real
MCP client session instead of a blocking run_mcp() loop.
"""

import json

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec

mcp_shared = pytest.importorskip("mcp.shared.memory")

from openagentmesh._mcp import build_mcp_server  # noqa: E402


class SummarizeInput(BaseModel):
    text: str


class SummarizeOutput(BaseModel):
    summary: str


def _register_recipe_agents(mesh: AgentMesh) -> None:
    @mesh.agent(
        AgentSpec(name="nlp.summarizer", description="Summarizes text"), mcp=True
    )
    async def summarize(req: SummarizeInput) -> SummarizeOutput:
        return SummarizeOutput(summary=req.text[:100])

    @mesh.agent(AgentSpec(name="internal.audit", description="Plumbing"), mcp=False)
    async def audit(req: SummarizeInput) -> SummarizeOutput:
        return SummarizeOutput(summary="internal")


class TestMCPBridgeRecipe:
    async def test_opt_in_policy_exports_only_flagged_agent(self):
        async with AgentMesh.local() as mesh:
            _register_recipe_agents(mesh)
            server = build_mcp_server(mesh, default_mcp=False)
            async with mcp_shared.create_connected_server_and_client_session(
                server
            ) as session:
                tools = (await session.list_tools()).tools
                assert [t.name for t in tools] == ["nlp_summarizer"]

    async def test_client_calls_exported_agent(self):
        async with AgentMesh.local() as mesh:
            _register_recipe_agents(mesh)
            server = build_mcp_server(mesh, default_mcp=False)
            async with mcp_shared.create_connected_server_and_client_session(
                server
            ) as session:
                result = await session.call_tool(
                    "nlp_summarizer", {"text": "hello mesh"}
                )
                assert result.isError is False
                assert json.loads(result.content[0].text) == {"summary": "hello mesh"}
