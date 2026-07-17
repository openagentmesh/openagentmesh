"""End-to-end MCP bridge test over real stdio (ADR-0002 exit proof).

Spawns `oam mcp serve` as a subprocess — exactly what an MCP client like
Claude Code launches — and drives it with the official SDK's stdio client
against a live mesh hosting a real agent.
"""

import json
import sys

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from mcp.types import TextContent  # noqa: E402


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    reply: str


async def test_stdio_client_lists_and_calls_mesh_agent():
    async with AgentMesh.local() as host:

        @host.agent(AgentSpec(name="echo", description="Echoes messages"), mcp=True)
        async def echo(req: EchoInput) -> EchoOutput:
            return EchoOutput(reply=f"Echo: {req.message}")

        await host.call("echo", {"message": "warmup"})  # flush registration

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "openagentmesh.cli", "mcp", "serve", "--url", host.url],
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            tools = (await session.list_tools()).tools
            assert "echo" in [t.name for t in tools]

            result = await session.call_tool("echo", {"message": "hello"})
            assert result.isError is False
            content = result.content[0]
            assert isinstance(content, TextContent)
            assert json.loads(content.text) == {"reply": "Echo: hello"}
