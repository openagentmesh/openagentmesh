"""`oam ui` command: static-asset server for the admin UI (ADR-0056 amended).

Phase 1 admin UI is a static React/TS bundle served from
``src/openagentmesh/_ui_assets/`` plus a single ``GET /config.json`` endpoint
that tells the browser where to open its NATS WebSocket connection. No
third-party HTTP framework -- stdlib ``http.server`` is enough for the
~30 LoC backend the amendment specifies.

Port assignments in Phase 1 (D-15, D-16):

* ``8088`` -- ``oam ui`` HTTP server (this file). The default is intentionally
  distinct from ``4223`` so it cannot collide with the embedded NATS
  WebSocket listener.
* ``4223`` -- embedded NATS WebSocket listener that the browser connects to
  *after* fetching ``/config.json``.

Resolution chain for ``nats_ws_url`` (D-16): ``--nats-ws-url`` flag >
``OAM_NATS_WS_URL`` env var > ``ws://127.0.0.1:4223`` default.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import typer

UI_ASSETS_DIR = Path(__file__).resolve().parents[1] / "_ui_assets"
DEFAULT_PORT = 8088  # oam ui HTTP server; chosen to NOT collide with NATS WS on 4223
DEFAULT_NATS_WS_URL = "ws://127.0.0.1:4223"


def _resolve_ws_url(flag_value: str | None) -> str:
    """Resolve the browser's NATS WS URL: flag > env > default."""
    if flag_value:
        return flag_value
    env = os.environ.get("OAM_NATS_WS_URL")
    if env:
        return env
    return DEFAULT_NATS_WS_URL


def _free_port_after(start: int) -> int:
    """Find the first free TCP port >= ``start`` (search up to +100)."""
    port = start
    while port < start + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    return start  # give up, let HTTPServer raise the actual bind error


def _make_handler(assets_dir: Path, ws_url: str) -> type:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(assets_dir), **kwargs)

        def do_GET(self) -> None:  # noqa: N802 (stdlib API)
            if self.path == "/config.json" or self.path.startswith("/config.json?"):
                body = json.dumps({"nats_ws_url": ws_url}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            # SPA history-mode fallback: serve index.html for non-asset 404s.
            requested = (assets_dir / self.path.lstrip("/")).resolve()
            if not requested.exists() and not self.path.startswith("/assets/"):
                self.path = "/index.html"
            return super().do_GET()

        def log_message(self, fmt, *args) -> None:  # noqa: A003 (stdlib API)
            # Quieter logging; prefix-tagged so the wildfire orchestrator's
            # honcho-style stdout multiplexer reads cleanly.
            sys.stderr.write("[oam-ui] " + (fmt % args) + "\n")

    return Handler


def ui(
    port: int = typer.Option(
        DEFAULT_PORT,
        "--port",
        "-p",
        help=(
            "HTTP port for the admin UI (default 8088; chosen to avoid "
            "collision with NATS WebSocket listener on 4223)."
        ),
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind address (defaults to localhost).",
    ),
    nats_ws_url: str | None = typer.Option(
        None,
        "--nats-ws-url",
        help=(
            "NATS WebSocket URL the browser should connect to. "
            "Defaults to ws://127.0.0.1:4223 or $OAM_NATS_WS_URL."
        ),
    ),
) -> None:
    """Serve the OpenAgentMesh admin UI (static assets + /config.json)."""
    index = UI_ASSETS_DIR / "index.html"
    if not index.exists():
        typer.echo(
            "Admin UI assets not found at "
            f"{UI_ASSETS_DIR}\n"
            "Run `pnpm run build` in the `ui/` directory to populate them, "
            "then re-run `oam ui`.",
            err=True,
        )
        raise typer.Exit(2)

    ws_url = _resolve_ws_url(nats_ws_url)

    # Port-fallback semantics per ADR-0056 amendment: try the requested port,
    # walk up to +100 if busy, surface the actual port we landed on.
    chosen = _free_port_after(port)
    if chosen != port:
        typer.echo(f"Port {port} busy; using {chosen} instead.", err=True)

    handler_cls = _make_handler(UI_ASSETS_DIR, ws_url)
    server = HTTPServer((host, chosen), handler_cls)
    url = f"http://{host}:{chosen}"
    typer.echo(f"Admin UI running at {url}")
    typer.echo(f"Browser will connect to NATS WebSocket at {ws_url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


__all__ = ["ui", "DEFAULT_PORT", "DEFAULT_NATS_WS_URL", "UI_ASSETS_DIR"]
