"""Tests for the MCP export bridge (ADR-0002 v1, ADR-0003 flag semantics).

A real MCP client (the official SDK's ClientSession) talks to the bridge
server over in-memory streams — the same protocol exchange as stdio, minus
the subprocess.
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


class AuditInput(BaseModel):
    event: str


class AuditOutput(BaseModel):
    ok: bool


def _register_agents(mesh: AgentMesh, *, summarizer_mcp=None, audit_mcp=None):
    @mesh.agent(
        AgentSpec(name="nlp.summarizer", description="Summarizes text"),
        mcp=summarizer_mcp,
    )
    async def summarize(req: SummarizeInput) -> SummarizeOutput:
        return SummarizeOutput(summary=req.text[:10])

    @mesh.agent(
        AgentSpec(name="internal.audit", description="Plumbing"),
        mcp=audit_mcp,
    )
    async def audit(req: AuditInput) -> AuditOutput:
        return AuditOutput(ok=True)


async def _client(mesh: AgentMesh, default_mcp: bool):
    server = build_mcp_server(mesh, default_mcp=default_mcp)
    return mcp_shared.create_connected_server_and_client_session(server)


class TestExportSelection:
    async def test_opt_in_exports_only_flagged_agents(self):
        async with AgentMesh.local() as mesh:
            _register_agents(mesh, summarizer_mcp=True)
            async with await _client(mesh, default_mcp=False) as session:
                tools = (await session.list_tools()).tools
                assert [t.name for t in tools] == ["nlp_summarizer"]

    async def test_opt_out_exports_everything_unless_disabled(self):
        async with AgentMesh.local() as mesh:
            _register_agents(mesh, audit_mcp=False)
            async with await _client(mesh, default_mcp=True) as session:
                names = {t.name for t in (await session.list_tools()).tools}
                assert "nlp_summarizer" in names
                assert "internal_audit" not in names

    async def test_tool_carries_description_and_schema(self):
        async with AgentMesh.local() as mesh:
            _register_agents(mesh, summarizer_mcp=True)
            async with await _client(mesh, default_mcp=False) as session:
                tool = (await session.list_tools()).tools[0]
                assert tool.description.startswith("Summarizes text")
                assert "text" in tool.inputSchema["properties"]

    async def test_non_invocable_agents_are_not_exported(self):
        async with AgentMesh.local() as mesh:

            @mesh.agent(
                AgentSpec(name="feed.ticker", description="Publishes prices"),
                mcp=True,
            )
            async def ticker() -> SummarizeOutput:
                yield SummarizeOutput(summary="x")

            async with await _client(mesh, default_mcp=True) as session:
                names = {t.name for t in (await session.list_tools()).tools}
                assert "feed_ticker" not in names


class TestToolCall:
    async def test_call_proxies_to_mesh_agent(self):
        async with AgentMesh.local() as mesh:
            _register_agents(mesh, summarizer_mcp=True)
            async with await _client(mesh, default_mcp=False) as session:
                result = await session.call_tool(
                    "nlp_summarizer", {"text": "hello world, this is long"}
                )
                assert result.isError is False
                payload = json.loads(result.content[0].text)
                assert payload == {"summary": "hello worl"}

    async def test_invalid_input_surfaces_as_tool_error(self):
        async with AgentMesh.local() as mesh:
            _register_agents(mesh, summarizer_mcp=True)
            async with await _client(mesh, default_mcp=False) as session:
                result = await session.call_tool("nlp_summarizer", {"wrong": 1})
                assert result.isError is True
                assert "invalid_input" in result.content[0].text

    async def test_unknown_tool_is_an_error(self):
        async with AgentMesh.local() as mesh:
            _register_agents(mesh)
            async with await _client(mesh, default_mcp=True) as session:
                result = await session.call_tool("no_such_tool", {})
                assert result.isError is True

    async def test_remote_agent_is_exported_too(self):
        """The bridge is a mesh gateway: agents registered by another
        process (contract carries x-agentmesh.mcp) are listed and callable."""
        async with AgentMesh.local() as host:
            _register_agents(host, summarizer_mcp=True)
            async with AgentMesh(host.url) as gateway:
                async with await _client(gateway, default_mcp=False) as session:
                    names = {t.name for t in (await session.list_tools()).tools}
                    assert "nlp_summarizer" in names
                    result = await session.call_tool(
                        "nlp_summarizer", {"text": "hello world!"}
                    )
                    assert result.isError is False
