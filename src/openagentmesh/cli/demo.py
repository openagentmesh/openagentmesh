"""`oam demo` commands: run cookbook recipes (ADR-0041)."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil

import typer

from .. import demos as demos_pkg
from .._mesh import AgentMesh

demo_app = typer.Typer(
    name="demo",
    help="Run, list, and inspect cookbook demo recipes.",
    no_args_is_help=True,
)


def _discover_demos() -> dict[str, type[object]]:
    """Find all demo modules in the demos package."""
    found = {}
    for info in pkgutil.iter_modules(demos_pkg.__path__):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"openagentmesh.demos.{info.name}")
        if hasattr(mod, "main") and asyncio.iscoroutinefunction(mod.main):
            found[info.name] = mod
    return found


def _get_demo(name: str):
    demos = _discover_demos()
    if name not in demos:
        typer.echo(f"Unknown demo: {name}", err=True)
        typer.echo(f"Available: {', '.join(sorted(demos))}", err=True)
        raise typer.Exit(1)
    return demos[name]


@demo_app.command("list")
def list_demos() -> None:
    """List available demos."""
    demos = _discover_demos()
    if not demos:
        typer.echo("No demos found.")
        return

    max_name = max(len(n) for n in demos)
    for name, mod in sorted(demos.items()):
        desc = (mod.__doc__ or "").strip().split("\n")[0]
        typer.echo(f"  {name:<{max_name}}  {desc}")


@demo_app.command("show")
def show(name: str = typer.Argument(..., help="Demo name.")) -> None:
    """Print the source code of a demo."""
    mod = _get_demo(name)
    source = inspect.getsource(mod)
    typer.echo(source)


@demo_app.command("run")
def run(name: str = typer.Argument(..., help="Demo name.")) -> None:
    """Run a demo against a temporary local mesh."""
    mod = _get_demo(name)

    async def _run() -> None:
        async with AgentMesh.local() as mesh:
            await mod.main(mesh)

    asyncio.run(_run())
