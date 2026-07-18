"""`oam observe` commands: tail logs and manage observability config (ADR-0048)."""

from __future__ import annotations

import asyncio
import json

import typer

from .._errors import MeshError
from .._mesh import AgentMesh
from .._observe import GLOBAL_KEY, LEVELS
from ._config import resolve_url
from ._output import as_json

observe_app = typer.Typer(
    name="observe",
    help="Tail mesh log events and control per-agent log levels.",
    no_args_is_help=True,
)


def _format_event(event) -> str:
    parts = [f"{event.timestamp} [{event.level}] {event.agent} {event.event}"]
    if event.request_id:
        parts.append(f"request_id={event.request_id}")
    if event.message:
        parts.append(f"— {event.message}")
    if event.data:
        parts.append(json.dumps(event.data))
    return " ".join(parts)


@observe_app.command("logs")
def logs(
    agent: str | None = typer.Argument(None, help="Agent name; omit for all agents."),
    level: str | None = typer.Option(
        None, "--level", help=f"Minimum level to show ({', '.join(LEVELS)})."
    ),
    url_flag: str | None = typer.Option(None, "--url", help="Override mesh URL."),
) -> None:
    """Tail log events from the mesh (Ctrl-C to stop)."""
    if level is not None and level not in LEVELS:
        typer.echo(
            f"Unknown level '{level}'. Choose from: {', '.join(LEVELS)}.", err=True
        )
        raise typer.Exit(2)
    url = resolve_url(url_flag)

    async def _run() -> None:
        async with AgentMesh(url) as mesh:
            async for event in mesh.observe.logs(agent, level=level):
                typer.echo(_format_event(event))

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except MeshError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@observe_app.command("config")
def config(
    agent: str | None = typer.Argument(
        None, help="Agent name for effective config; omit to list everything."
    ),
    json_flag: bool = typer.Option(False, "--json", help="JSON output."),
    url_flag: str | None = typer.Option(None, "--url", help="Override mesh URL."),
) -> None:
    """Show observability config (global default plus per-agent overrides)."""
    url = resolve_url(url_flag)

    async def _run() -> dict:
        async with AgentMesh(url) as mesh:
            if agent is not None:
                cfg = await mesh.observe.get(agent)
                return cfg.model_dump()

            kv = mesh._observe_kv_required
            try:
                keys = await kv.keys()
            except Exception:
                keys = []  # empty bucket
            agents: dict[str, dict] = {}
            global_config = {"log_level": "info"}
            for key in keys:
                try:
                    entry = await kv.get(key)
                    value = json.loads(entry.value or b"{}")
                except Exception:
                    continue
                if key == GLOBAL_KEY:
                    global_config = value
                else:
                    agents[key] = value
            return {"global": global_config, "agents": agents}

    try:
        result = asyncio.run(_run())
    except MeshError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if json_flag:
        typer.echo(as_json(result))
    elif agent is not None:
        typer.echo(f"{agent}: log_level={result['log_level']} (source: {result['source']})")
    else:
        typer.echo(f"global: log_level={result['global'].get('log_level', 'info')}")
        for name, cfg in sorted(result["agents"].items()):
            typer.echo(f"{name}: log_level={cfg.get('log_level', '?')}")


@observe_app.command("set")
def set_config(
    agent: str | None = typer.Argument(None, help="Agent name to configure."),
    log_level: str = typer.Option(..., "--log-level", help=f"One of: {', '.join(LEVELS)}."),
    global_flag: bool = typer.Option(
        False, "--global", help="Set the mesh-wide default instead of one agent."
    ),
    url_flag: str | None = typer.Option(None, "--url", help="Override mesh URL."),
) -> None:
    """Set the log level for one agent or mesh-wide (applies live, no restart)."""
    if (agent is None) == (not global_flag):
        typer.echo("Provide an agent name or --global (not both).", err=True)
        raise typer.Exit(2)
    if log_level not in LEVELS:
        typer.echo(
            f"Unknown log_level '{log_level}'. Choose from: {', '.join(LEVELS)}.", err=True
        )
        raise typer.Exit(2)
    url = resolve_url(url_flag)

    async def _run() -> None:
        async with AgentMesh(url) as mesh:
            if global_flag:
                await mesh.observe.set_global(log_level=log_level)
            else:
                assert agent is not None
                await mesh.observe.set(agent, log_level=log_level)

    try:
        asyncio.run(_run())
    except MeshError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    target = "global" if global_flag else agent
    typer.echo(f"{target}: log_level={log_level}")
