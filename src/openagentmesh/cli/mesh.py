"""`oam mesh` commands: lifecycle and inspection (ADR-0033)."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

import typer

from .._local import AGENTMESH_DIR, download_nats_server, find_nats_server
from .._mesh import AgentMesh
from ._config import OAM_URL_FILE, resolve_url, write_url_file
from ._output import as_json, table

mesh_app = typer.Typer(
    name="mesh",
    help="Manage the local mesh and inspect a connected mesh.",
    no_args_is_help=True,
)

RUN_DIR = AGENTMESH_DIR / "run"
PID_FILE = RUN_DIR / "oam-mesh.pid"
LOG_FILE = RUN_DIR / "oam-mesh.log"
DATA_DIR = RUN_DIR / "data"


def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (ConnectionRefusedError, OSError):
            return False


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_pid() -> int | None:
    if not PID_FILE.is_file():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
    except ValueError:
        return None
    return pid if pid > 0 else None


async def _resolve_binary() -> Path:
    binary = find_nats_server()
    if binary is None:
        binary = await download_nats_server()
    return binary


async def _prime_buckets(url: str) -> None:
    """Briefly connect an AgentMesh to create KV buckets (idempotent)."""
    async with AgentMesh(url):
        pass


async def _wait_for_catalog_populated(mesh: AgentMesh, timeout: float = 2.0) -> None:
    """Let the catalog watcher drain the current KV state into the cache.

    `mesh.catalog()` reads from a cache populated asynchronously by the watcher.
    For short-lived CLI invocations we must poll the KV directly so we do not
    report an empty catalog just because the watcher has not fired yet.
    """
    import json as _json

    assert mesh._catalog_kv is not None
    try:
        kv_entry = await mesh._catalog_kv.get("catalog")
    except Exception:
        return
    if kv_entry.value:
        from .._models import CatalogEntry

        mesh._catalog_cache = {
            e["name"]: CatalogEntry.model_validate(e)
            for e in _json.loads(kv_entry.value)
        }


async def _wait_for_ready(url: str, timeout: float = 5.0) -> None:
    """Poll the NATS TCP port until it accepts connections (quiet probe)."""
    import contextlib
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 4222

    deadline = asyncio.get_event_loop().time() + timeout
    last_exc: Exception | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            _reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            return
        except (ConnectionRefusedError, OSError) as exc:
            last_exc = exc
            await asyncio.sleep(0.1)
    raise RuntimeError(f"NATS at {url} did not become ready: {last_exc}")


@mesh_app.command("up")
def up(
    port: int = typer.Option(4222, "--port", "-p", help="Port to bind NATS."),
    foreground: bool = typer.Option(
        False, "--foreground", "-f", help="Run in foreground; blocks until interrupted."
    ),
) -> None:
    """Start a local NATS server with JetStream and pre-create KV buckets."""
    existing = _read_pid()
    if existing and _process_alive(existing):
        typer.echo(f"Mesh already running (pid {existing}). Use `oam mesh down` first.", err=True)
        raise typer.Exit(1)
    if existing:
        PID_FILE.unlink(missing_ok=True)

    if _port_in_use(port):
        typer.echo(
            f"Port {port} is already in use. "
            f"Another NATS or service may be running. Check: lsof -i :{port}",
            err=True,
        )
        raise typer.Exit(1)

    binary = asyncio.run(_resolve_binary())
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    log_fh = LOG_FILE.open("ab")
    popen_kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_fh,
        "stderr": log_fh,
    }
    if not foreground and sys.platform != "win32":
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(
        [str(binary), "-p", str(port), "-js", "--store_dir", str(DATA_DIR)],
        **popen_kwargs,
    )

    url = f"nats://127.0.0.1:{port}"
    try:
        asyncio.run(_wait_for_ready(url))
    except Exception as exc:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        typer.echo(f"Failed to start mesh: {exc}", err=True)
        raise typer.Exit(1) from exc

    if proc.poll() is not None:
        typer.echo(
            f"NATS exited immediately. Check {LOG_FILE} for details.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        asyncio.run(_prime_buckets(url))
    except Exception as exc:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        typer.echo(f"Failed to prime KV buckets: {exc}", err=True)
        raise typer.Exit(1) from exc

    PID_FILE.write_text(str(proc.pid))
    write_url_file(url)

    from ._output import banner
    typer.echo(banner())
    typer.echo(f"  NATS listening on {url}")
    typer.echo("  KV buckets ready: mesh-catalog, mesh-registry, mesh-context")
    typer.echo(f"  Wrote {OAM_URL_FILE}")

    if foreground:
        def _stop(_signum, _frame):
            proc.terminate()

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
        exit_code = proc.wait()
        PID_FILE.unlink(missing_ok=True)
        raise typer.Exit(exit_code if exit_code >= 0 else 0)


@mesh_app.command("down")
def down() -> None:
    """Stop the local mesh started by `oam mesh up`."""
    pid = _read_pid()
    if pid is None:
        typer.echo("No running mesh recorded.", err=True)
        raise typer.Exit(1)

    if not _process_alive(pid):
        typer.echo(f"Stale PID file (pid {pid} not running). Cleaning up.")
        PID_FILE.unlink(missing_ok=True)
        return

    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not _process_alive(pid):
            break
        import time
        time.sleep(0.1)
    else:
        os.kill(pid, signal.SIGKILL)

    PID_FILE.unlink(missing_ok=True)
    typer.echo(f"Stopped mesh (pid {pid}).")


@mesh_app.command("connect")
def connect(url: str = typer.Argument(..., help="NATS URL, e.g. nats://host:4222")) -> None:
    """Point subsequent `oam` commands at a mesh by writing `.oam-url`."""
    write_url_file(url)
    typer.echo(f"Wrote {OAM_URL_FILE}")


@mesh_app.command("catalog")
def catalog(
    url_flag: str | None = typer.Option(None, "--url", help="Override mesh URL."),
    channel: str | None = typer.Option(None, "--channel", help="Filter by channel prefix."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """List registered agents from the catalog."""
    url = resolve_url(url_flag)

    async def _run() -> list:
        async with AgentMesh(url) as mesh:
            await _wait_for_catalog_populated(mesh)
            return await mesh.catalog(channel=channel)

    entries = asyncio.run(_run())

    if json_out:
        typer.echo(as_json(entries))
        return

    rows = [
        [e.name, "yes" if e.streaming else "no", e.description]
        for e in entries
    ]
    typer.echo(table(rows, headers=["NAME", "STREAMING", "DESCRIPTION"]))


@mesh_app.command("listen")
def listen(
    channel: str = typer.Argument(..., help="NATS subject or wildcard, e.g. agent.*.out"),
    url_flag: str | None = typer.Option(None, "--url", help="Override mesh URL."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON lines."),
) -> None:
    """Tap a mesh subject (NATS wildcards supported) and stream messages."""
    import json as _json

    import nats

    url = resolve_url(url_flag)

    async def _run() -> None:
        nc = await nats.connect(url)
        try:
            async def handler(msg):
                if json_out:
                    try:
                        payload = _json.loads(msg.data) if msg.data else None
                    except Exception:
                        payload = msg.data.decode("utf-8", errors="replace")
                    typer.echo(as_json({"subject": msg.subject, "data": payload}))
                else:
                    data = msg.data.decode("utf-8", errors="replace") if msg.data else ""
                    typer.echo(f"[{msg.subject}] {data}")

            await nc.subscribe(channel, cb=handler)
            stop = asyncio.Event()

            def _halt(*_):
                stop.set()

            try:
                loop = asyncio.get_running_loop()
                loop.add_signal_handler(signal.SIGINT, _halt)
                loop.add_signal_handler(signal.SIGTERM, _halt)
            except NotImplementedError:
                pass

            await stop.wait()
        finally:
            await nc.close()

    import contextlib as _contextlib

    with _contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run())


__all__ = ["mesh_app"]
