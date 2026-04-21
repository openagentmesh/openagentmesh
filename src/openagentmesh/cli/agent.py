"""`oam agent` commands: invocation and inspection (ADR-0033)."""

from __future__ import annotations

import asyncio
import json
import sys

import typer

from .._mesh import AgentMesh
from .._models import InvocationMismatch, MeshError
from ._config import resolve_url
from ._output import as_json

agent_app = typer.Typer(
    name="agent",
    help="Invoke and query contracts of individual agents on the mesh.",
    no_args_is_help=True,
)


def _read_payload(payload_arg: str | None) -> dict | list | str | int | float | bool | None:
    """Load payload from positional arg, else stdin, else empty."""
    raw: str | None
    if payload_arg is not None:
        raw = payload_arg
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        raw = None

    if raw is None or not raw.strip():
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON payload: {exc}", err=True)
        raise typer.Exit(2) from exc


def _cli_hint(exc: MeshError, agent_name: str) -> str | None:
    if not isinstance(exc, InvocationMismatch):
        return None
    msg = exc.message.lower()
    if "subscribe" in msg:
        return f"oam agent subscribe {agent_name}"
    if "stream()" in msg:
        return f"oam agent stream {agent_name} [payload]"
    if "call()" in msg:
        return f"oam agent call {agent_name} [payload]"
    return None


def _emit_mesh_error(exc: MeshError, agent_name: str = "") -> None:
    typer.echo(f"Error [{exc.code}] {exc}", err=True)
    if exc.details:
        typer.echo(as_json(exc.details), err=True)
    if agent_name:
        hint = _cli_hint(exc, agent_name)
        if hint:
            typer.echo(f"\nTry: {hint}", err=True)


@agent_app.command("call")
def call(
    name: str = typer.Argument(..., help="Agent name."),
    payload: str | None = typer.Argument(None, help="JSON payload. Reads stdin if omitted."),
    url_flag: str | None = typer.Option(None, "--url", help="Override mesh URL."),
    timeout: float = typer.Option(30.0, "--timeout", help="Seconds before timing out."),
    json_out: bool = typer.Option(
        False, "--json", help="Pretty-print the response as JSON.",
    ),
) -> None:
    """Invoke an agent and print its response."""
    url = resolve_url(url_flag)
    data = _read_payload(payload)

    async def _run() -> dict:
        async with AgentMesh(url) as mesh:
            return await mesh.call(name, data, timeout=timeout)

    try:
        result = asyncio.run(_run())
    except MeshError as exc:
        _emit_mesh_error(exc, agent_name=name)
        raise typer.Exit(1) from exc

    if json_out:
        typer.echo(as_json(result))
    else:
        typer.echo(json.dumps(result))


@agent_app.command("stream")
def stream(
    name: str = typer.Argument(..., help="Agent name."),
    payload: str | None = typer.Argument(None, help="JSON payload. Reads stdin if omitted."),
    url_flag: str | None = typer.Option(None, "--url", help="Override mesh URL."),
    timeout: float = typer.Option(60.0, "--timeout", help="Seconds before timing out."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON per chunk."),
) -> None:
    """Invoke a streaming agent and print each chunk as it arrives."""
    url = resolve_url(url_flag)
    data = _read_payload(payload)

    async def _run() -> None:
        async with AgentMesh(url) as mesh:
            async for chunk in mesh.stream(name, data, timeout=timeout):
                if json_out:
                    typer.echo(as_json(chunk))
                else:
                    typer.echo(json.dumps(chunk))

    try:
        asyncio.run(_run())
    except MeshError as exc:
        _emit_mesh_error(exc, agent_name=name)
        raise typer.Exit(1) from exc


@agent_app.command("subscribe")
def subscribe(
    name: str = typer.Argument(..., help="Agent name (publisher)."),
    url_flag: str | None = typer.Option(None, "--url", help="Override mesh URL."),
    timeout: float | None = typer.Option(None, "--timeout", help="Seconds between events before giving up."),
    json_out: bool = typer.Option(False, "--json", help="Pretty-print each event as JSON."),
) -> None:
    """Subscribe to a publisher agent's event stream."""
    url = resolve_url(url_flag)

    async def _run() -> None:
        async with AgentMesh(url) as mesh:
            async for event in mesh.subscribe(agent=name, timeout=timeout):
                if json_out:
                    typer.echo(as_json(event))
                else:
                    typer.echo(json.dumps(event))

    try:
        asyncio.run(_run())
    except MeshError as exc:
        _emit_mesh_error(exc, agent_name=name)
        raise typer.Exit(1) from exc


@agent_app.command("contract")
def contract(
    name: str = typer.Argument(..., help="Agent name."),
    url_flag: str | None = typer.Option(None, "--url", help="Override mesh URL."),
    json_out: bool = typer.Option(True, "--json/--text", help="JSON (default) or text summary."),
) -> None:
    """Fetch and display an agent's contract."""
    url = resolve_url(url_flag)

    async def _run():
        async with AgentMesh(url) as mesh:
            return await mesh.contract(name)

    try:
        contract = asyncio.run(_run())
    except MeshError as exc:
        _emit_mesh_error(exc)
        raise typer.Exit(1) from exc

    if json_out:
        typer.echo(as_json(contract))
        return

    typer.echo(f"name:        {contract.name}")
    typer.echo(f"description: {contract.description}")
    typer.echo(f"version:     {contract.version}")
    typer.echo(f"channel:     {contract.channel or '-'}")
    typer.echo(f"streaming:   {'yes' if contract.streaming else 'no'}")
    typer.echo(f"invocable:   {'yes' if contract.invocable else 'no'}")
    if contract.tags:
        typer.echo(f"tags:        {', '.join(contract.tags)}")


__all__ = ["agent_app"]
