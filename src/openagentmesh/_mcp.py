"""MCP export bridge: serve mesh agents to MCP clients (ADR-0002 v1).

Requires the ``mcp`` extra: ``pip install 'openagentmesh[mcp]'``.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

try:
    import mcp.types as mcp_types
    from mcp.server.lowlevel import Server
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "The MCP bridge requires the 'mcp' extra: pip install 'openagentmesh[mcp]'"
    ) from e

from ._errors import MeshError
from ._models import AgentContract

if TYPE_CHECKING:
    from ._mesh import AgentMesh

_log = logging.getLogger("openagentmesh")


def build_mcp_server(mesh: AgentMesh, *, default_mcp: bool = True) -> Server:
    """Build an MCP server that proxies ``tools/list``/``tools/call`` to the mesh.

    The server is a gateway to the whole mesh: any invocable agent whose
    contract opts in (``mcp=True``, or unset under ``default_mcp=True``) is
    exported, wherever it is hosted. Streamers and publishers are skipped in
    v1 (no request/reply semantics over MCP yet).
    """
    server = Server("openagentmesh")
    # tool name (sanitized) -> agent name; rebuilt on every tools/list
    name_map: dict[str, str] = {}

    async def _exported_contracts() -> list[AgentContract]:
        exported = []
        for contract in await mesh.discover():
            if not contract.invocable or contract.streaming:
                continue
            opted_in = contract.mcp if contract.mcp is not None else default_mcp
            if opted_in:
                exported.append(contract)
        return exported

    async def _refresh_tools() -> list[mcp_types.Tool]:
        tools = []
        name_map.clear()
        for contract in await _exported_contracts():
            schema = contract.to_tool_schema()
            name_map[schema["name"]] = contract.name
            tools.append(
                mcp_types.Tool(
                    name=schema["name"],
                    description=schema["description"],
                    inputSchema=schema["input_schema"],
                )
            )
        return tools

    @server.list_tools()
    async def _list_tools() -> list[mcp_types.Tool]:
        return await _refresh_tools()

    @server.call_tool()
    async def _call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[mcp_types.TextContent]:
        if name not in name_map:
            await _refresh_tools()
        agent = name_map.get(name)
        if agent is None:
            raise ValueError(f"Unknown tool '{name}'")
        try:
            result = await mesh.call(agent, arguments)
        except MeshError as e:
            # The taxonomy code (ADR-0057) leads the message so clients can
            # distinguish caller faults from provider faults.
            raise ValueError(f"{e.code}: {e.message}") from e
        return [mcp_types.TextContent(type="text", text=json.dumps(result))]

    return server


async def serve_mcp(mesh: AgentMesh, *, default_mcp: bool = True) -> None:
    """Serve the mesh over MCP stdio until the client disconnects.

    Connects the mesh (hosting any registered agents) for the duration.
    """
    from mcp.server.stdio import stdio_server

    server = build_mcp_server(mesh, default_mcp=default_mcp)
    async with mesh, stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
