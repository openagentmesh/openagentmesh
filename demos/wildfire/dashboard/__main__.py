"""Uvicorn entry point for the wildfire dashboard backend.

Per ``.planning/phases/02-cascade-closure/02-CONTEXT.md`` decisions:

- D-37: ``python -m demos.wildfire.dashboard`` boots the FastAPI app via
  uvicorn programmatically (one shot; no separate uvicorn invocation).
- D-39: default port is ``DASHBOARD_PORT`` (8081) with auto-fallback to
  the next free port if occupied. The resolved URL prints to stdout on
  boot so the orchestrator (and the viewer) sees exactly where to point.
- D-36: if ``dist/index.html`` is missing the bundle has not been built;
  the server prints a clear "run pnpm run build" message to stderr and
  exits 2 before opening any sockets.

Boot sequence:

1. parse argv (--host, --port).
2. resolve a free port (walk up from the requested one).
3. verify ``dist/index.html`` exists (or fail fast).
4. connect AgentMesh to NATS (NATS_URL env var; default
   ``nats://127.0.0.1:4222``).
5. build the FastAPI app (``make_app``) and wire the four mesh consumers
   (``register_mesh_consumers``).
6. print ``dashboard at http://<host>:<port>`` to stdout.
7. run uvicorn programmatically; trap SIGTERM / SIGINT for clean shutdown.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import socket
import sys
from pathlib import Path

import uvicorn

from demos.wildfire.core.config import DASHBOARD_PORT
from openagentmesh import AgentMesh

from demos.wildfire.dashboard.server import (
    make_app,
    register_mesh_consumers,
)

_log = logging.getLogger("wildfire.dashboard")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def find_free_port(host: str, requested: int, *, max_walk: int = 100) -> int:
    """Return ``requested`` if free, else walk up to ``requested + max_walk``.

    Mirrors the port-fallback policy in ``src/openagentmesh/_local.py`` (D-39
    invariant). The probe binds a transient socket; success means the port
    was free at probe time. There is an inherent TOCTOU race between probe
    and the uvicorn bind, but the orchestrator boot is not concurrent with
    other dashboard instances, so the race is benign in practice.
    """
    for offset in range(max_walk + 1):
        port = requested + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # SO_REUSEADDR matches uvicorn's own bind semantics; without it a
            # TIME_WAIT socket from the previous run reads as busy and every
            # restart silently walks to the next port.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
            except OSError:
                continue
        return port
    raise RuntimeError(
        f"no free port in [{requested}, {requested + max_walk}] on {host}"
    )


def _verify_dist_or_exit() -> Path:
    """Verify ``demos/wildfire/dashboard/dist/index.html`` exists.

    On failure print the pnpm hint to stderr and ``sys.exit(2)`` (D-36).
    Returns the resolved dist directory on success so the caller can pass
    it on to ``make_app`` if needed (currently make_app re-derives the
    same path; this exists to ensure the boot path fails fast before any
    NATS connection attempt).
    """
    dist_dir = Path(__file__).parent / "dist"
    index = dist_dir / "index.html"
    if not index.is_file():
        print(
            "dashboard bundle missing: run pnpm run build in "
            "demos/wildfire/dashboard/",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return dist_dir


# ---------------------------------------------------------------------------
# serve / main
# ---------------------------------------------------------------------------


async def serve(*, host: str = "127.0.0.1", port: int = DASHBOARD_PORT) -> None:
    """Boot the dashboard backend.

    The dist guard runs FIRST so a missing-bundle deployment fails before
    any NATS connection attempt (cheap, fast, friendly). Then we resolve
    a free port, connect the mesh, build the app, and run uvicorn.
    """
    _verify_dist_or_exit()

    actual_port = find_free_port(host, port)
    nats_url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")

    mesh = AgentMesh(nats_url)

    # Wire SIGTERM/SIGINT to a clean-shutdown event so the orchestrator's
    # Popen.terminate() (SIGTERM) on shutdown unblocks server.serve() the
    # same way Ctrl-C does. add_signal_handler is best-effort: not all
    # platforms / contexts support it.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop_event.set)

    async with mesh:
        app = make_app(mesh)
        register_mesh_consumers(mesh, app.state.broadcast)
        await mesh._subscribe_pending()  # bind the four sources we just registered.

        config = uvicorn.Config(
            app,
            host=host,
            port=actual_port,
            log_level="warning",
            lifespan="on",
        )
        server = uvicorn.Server(config)

        # Print the resolved URL on stdout so the viewer (and the
        # orchestrator) knows exactly where to connect (D-39).
        print(f"dashboard at http://{host}:{actual_port}", flush=True)

        # Run uvicorn and the stop_event listener concurrently. Whichever
        # finishes first triggers cancellation of the other.
        serve_task = asyncio.create_task(server.serve())
        stop_task = asyncio.create_task(stop_event.wait())
        try:
            done, pending = await asyncio.wait(
                {serve_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            if not serve_task.done():
                # Clean uvicorn shutdown: flag the server, await its task.
                server.should_exit = True
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.wait_for(serve_task, timeout=5)
            if not stop_task.done():
                stop_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stop_task


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="demos.wildfire.dashboard")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind host (default: 127.0.0.1; T-02-05-03 mitigation).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DASHBOARD_PORT,
        help=(
            f"Requested HTTP port (default: {DASHBOARD_PORT}). "
            f"Falls back to next free port if busy."
        ),
    )
    args = parser.parse_args(argv)

    try:
        asyncio.run(serve(host=args.host, port=args.port))
    except KeyboardInterrupt:
        return 0
    except SystemExit:
        raise
    except Exception as e:
        print(f"dashboard failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
