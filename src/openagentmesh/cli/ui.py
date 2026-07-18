"""`oam ui`: serve the admin UI SPA and its bootstrap config (ADR-0056).

The server has exactly two responsibilities: serve the compiled frontend
assets from ``src/openagentmesh/_ui_assets/`` and answer ``GET /config.json``
with the NATS WebSocket URL the browser should connect to. The browser is a
first-class mesh client over nats.ws; there is no HTTP API in between.
"""

from __future__ import annotations

import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import typer

from ._config import resolve_url

DEFAULT_UI_PORT = 4224
ASSETS_DIR = Path(__file__).resolve().parent.parent / "_ui_assets"

MISSING_ASSETS_HINT = (
    "No compiled UI assets found at {path}.\n"
    "Release wheels bundle them; in a source checkout run the Vite dev server "
    "instead: cd ui/ && pnpm install && pnpm dev"
)


class UIAssetsMissing(RuntimeError):
    """The compiled SPA is absent (source checkout without a UI build)."""


def derive_ws_url(mesh_url: str) -> str:
    """Default websocket URL for a mesh URL: same host, mesh port + 1.

    Matches the listener `oam mesh up` and `AgentMesh.local()` configure
    (the websocket listener cannot share the NATS client port).
    """
    parsed = urlparse(mesh_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 4222
    return f"ws://{host}:{port + 1}"


class _UIRequestHandler(SimpleHTTPRequestHandler):
    server: _UIHTTPServer  # type: ignore[assignment]

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path.split("?", 1)[0] == "/config.json":
            payload = json.dumps(self.server.config_payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def send_head(self):
        # SPA fallback: client-side routes (/agents/:name, /events) map to index.html.
        target = Path(self.translate_path(self.path))
        if not target.exists():
            self.path = "/"
        return super().send_head()

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - http.server API
        pass


class _UIHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, *, directory: Path, config_payload: dict):
        self.config_payload = config_payload
        self._directory = directory
        super().__init__(address, handler)

    def finish_request(self, request, client_address) -> None:
        _UIRequestHandler(request, client_address, self, directory=str(self._directory))


class UIServer:
    """Static server for the admin UI. Binds on start(); falls back to a free port."""

    def __init__(
        self,
        assets_dir: Path | str,
        *,
        nats_ws_url: str,
        host: str = "127.0.0.1",
        port: int = DEFAULT_UI_PORT,
    ) -> None:
        self.assets_dir = Path(assets_dir)
        if not (self.assets_dir / "index.html").is_file():
            raise UIAssetsMissing(MISSING_ASSETS_HINT.format(path=self.assets_dir))
        self.nats_ws_url = nats_ws_url
        self.host = host
        self.port = port
        self._httpd: _UIHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        payload = {"nats_ws_url": self.nats_ws_url}
        try:
            self._httpd = _UIHTTPServer(
                (self.host, self.port),
                _UIRequestHandler,
                directory=self.assets_dir,
                config_payload=payload,
            )
        except OSError:
            self._httpd = _UIHTTPServer(
                (self.host, 0),
                _UIRequestHandler,
                directory=self.assets_dir,
                config_payload=payload,
            )
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


def ui(
    port: int = typer.Option(DEFAULT_UI_PORT, "--port", "-p", help="Port to serve the UI."),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        envvar="OAM_UI_HOST",
        help="Bind address. Non-localhost exposes mesh write access; prefer an SSH tunnel.",
    ),
    nats_ws_url: str | None = typer.Option(
        None,
        "--nats-ws-url",
        envvar="OAM_NATS_WS_URL",
        help="NATS WebSocket URL handed to the browser (default: mesh URL, port + 1).",
    ),
    url_flag: str | None = typer.Option(None, "--url", help="Override mesh URL."),
    assets_dir: str | None = typer.Option(
        None, "--assets-dir", hidden=True, help="Compiled SPA location (default: bundled)."
    ),
    check: bool = typer.Option(
        False, "--check", help="Resolve and print the configuration, then exit."
    ),
) -> None:
    """Serve the admin UI (agent registry, invocation sandbox, event feed)."""
    resolved_assets = Path(assets_dir) if assets_dir else ASSETS_DIR
    resolved_ws_url = nats_ws_url or derive_ws_url(resolve_url(url_flag))

    try:
        server = UIServer(resolved_assets, nats_ws_url=resolved_ws_url, host=host, port=port)
    except UIAssetsMissing as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if check:
        typer.echo(f"UI assets: {resolved_assets}")
        typer.echo(f"Browser will connect to {resolved_ws_url} (NATS WebSocket)")
        return

    server.start()
    typer.echo(f"Admin UI running at {server.url}")
    typer.echo(f"Browser will connect to {resolved_ws_url} (NATS WebSocket)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


__all__ = ["UIAssetsMissing", "UIServer", "derive_ws_url", "ui"]
