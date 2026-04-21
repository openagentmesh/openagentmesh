"""OpenAgentMesh CLI (ADR-0033)."""

from __future__ import annotations

import typer

from .agent import agent_app
from .demo import demo
from .mesh import mesh_app

app = typer.Typer(
    name="oam",
    help="OpenAgentMesh command line interface.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(mesh_app, name="mesh")
app.add_typer(agent_app, name="agent")
app.command("demo")(demo)


@app.callback()
def _root() -> None:
    """oam: inspect and drive an OpenAgentMesh deployment."""


if __name__ == "__main__":
    app()
