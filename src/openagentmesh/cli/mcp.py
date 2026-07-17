"""`oam mcp` commands: serve the mesh to MCP clients (ADR-0002)."""

from __future__ import annotations

import typer

from .._mesh import AgentMesh
from ._config import resolve_url

mcp_app = typer.Typer(
    name="mcp",
    help="Bridge the mesh to the Model Context Protocol.",
    no_args_is_help=True,
)


@mcp_app.command("serve")
def serve(
    url: str | None = typer.Option(
        None, "--url", help="NATS URL of the mesh (defaults to the active local mesh)."
    ),
    default_mcp: bool = typer.Option(
        True,
        "--default-export/--no-default-export",
        help="Whether agents without an explicit mcp flag are exported.",
    ),
) -> None:
    """Serve mesh agents to an MCP client over stdio.

    Register with an MCP client, e.g.:

        claude mcp add mesh -- oam mcp serve
    """
    try:
        import mcp  # noqa: F401
    except ImportError:
        typer.echo(
            "The MCP bridge requires the 'mcp' extra: pip install 'openagentmesh[mcp]'",
            err=True,
        )
        raise typer.Exit(1) from None

    mesh = AgentMesh(resolve_url(url))
    mesh.run_mcp(default_mcp=default_mcp)
