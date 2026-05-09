"""Wildfire demo orchestrator (D-01, D-03, D-04, D-37, D-39).

Owns one process tree:

* embedded ``nats-server`` (HOCON config with WebSocket listener)
* fleet child processes (1 fire-sim + 1 uav + 5 drones + 1 heli + 3 ffunits +
  MEDEVAC_COUNT medevacs added in Phase 2 cascade closure)
* ``oam ui`` static-asset server (admin UI MVP, ADR-0056 amendment)
* scenario UI dashboard backend (``python -m demos.wildfire.dashboard``,
  Phase 2; default port DASHBOARD_PORT=8081 with auto-fallback per D-39)

Children are spawned via ``python -m`` with ``NATS_URL`` exported in their env;
they instantiate plain ``AgentMesh()`` and connect to the embedded bus. Stdout
and stderr from every child are line-multiplexed onto the orchestrator's own
stdout with a ``[<tag>]`` prefix (honcho-style).

Per A-02 (single-bucket world grid), the orchestrator does NOT pre-create any
JetStream KV namespace of its own. World state and fleet records live under
the OAM-internal ``mesh-context`` store with ``wildfire.*`` key prefixes;
``AgentMesh.__aenter__`` provisions ``mesh-context`` idempotently in each child.

Restart policy (Claude's discretion in 01-CONTEXT): no restart. Process exits
are logged, never retried -- death is visible, which sets up Phase 4 chaos.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import IO
from urllib.parse import urlparse

from openagentmesh._local import AGENTMESH_DIR, download_nats_server, find_nats_server

from .config import (
    DASHBOARD_PORT,
    DRONE_COUNT,
    FFUNIT_COUNT,
    HELI_COUNT,
    MEDEVAC_COUNT,
    UAV_COUNT,
)
from .nats_config import write_nats_config

# Logical fleet name -> (python -m module, instance count).
# The orchestrator does NOT import these modules; they are spawned as
# subprocesses, so they need not exist when the orchestrator class is imported.
# Counts come from ``demos.wildfire.core.config`` (D-08, plus MEDEVAC_COUNT
# from 02-CONTEXT.md SCN-07 for the Phase 2 cascade-closure fleet).
CHILD_SPECS: dict[str, tuple[str, int]] = {
    "fire-sim": ("demos.wildfire.world.fire_sim", 1),
    "uav": ("demos.wildfire.fleet.uav", UAV_COUNT),
    "drone": ("demos.wildfire.fleet.drone", DRONE_COUNT),
    "heli": ("demos.wildfire.fleet.heli", HELI_COUNT),
    "ffunit": ("demos.wildfire.fleet.ffunit", FFUNIT_COUNT),
    "medevac": ("demos.wildfire.fleet.medevac", MEDEVAC_COUNT),  # Phase 2 (SCN-07)
}


async def _wait_for_ready(url: str, timeout: float = 5.0) -> None:
    """Poll a NATS TCP port until it accepts connections.

    Mirrors ``openagentmesh.cli.mesh._wait_for_ready`` to avoid an import across
    the ``cli`` package boundary (which would pull in Typer at orchestrator
    boot time for no reason).
    """
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


class Orchestrator:
    """Boot embedded NATS, spawn fleet + admin UI + dashboard, supervise until SIGINT.

    Attributes:
        nats_port: Standard NATS listener port (clients).
        ws_port: WebSocket listener port (browser via ``nats.ws``).
        http_port: NATS monitoring HTTP endpoint.
        ui_port: ``oam ui`` static-asset server HTTP port (DEFAULTS TO 8088;
            MUST differ from ``ws_port`` to avoid the obvious collision).
        dashboard_port: scenario UI dashboard HTTP port (D-37, D-39). The
            dashboard process auto-falls back to the next free port if this
            one is busy; the orchestrator's banner prints the requested port
            (the resolved port is visible on the ``[dash]``-tagged log lines).
        run_dir: JetStream store directory + temp scratch space.
    """

    def __init__(
        self,
        *,
        nats_port: int = 4222,
        ws_port: int = 4223,
        http_port: int = 8222,
        ui_port: int = 8088,
        dashboard_port: int = DASHBOARD_PORT,
        run_dir: Path = AGENTMESH_DIR / "run" / "wildfire",
    ) -> None:
        self.nats_port = nats_port
        self.ws_port = ws_port
        self.http_port = http_port
        self.ui_port = ui_port
        self.dashboard_port = dashboard_port
        self.run_dir = run_dir
        self.nats_url = f"nats://127.0.0.1:{nats_port}"

        self._nats_proc: subprocess.Popen[bytes] | None = None
        self._children: dict[str, subprocess.Popen[bytes]] = {}
        self._ui_proc: subprocess.Popen[bytes] | None = None
        self._dash_proc: subprocess.Popen[bytes] | None = None
        self._config_path: Path | None = None
        self._stop = asyncio.Event()
        self._log_tasks: list[asyncio.Task[None]] = []

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _print(line: str) -> None:
        """Single point of stdout writes; flushes immediately for live feel."""
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    async def _drain(self, tag: str, stream: IO[bytes] | None) -> None:
        """Read ``stream`` line by line and echo with a ``[tag]`` prefix.

        Uses ``asyncio.to_thread`` so blocking ``readline`` calls do not stall
        the event loop. Returns when the stream is closed (child exit).
        """
        if stream is None:
            return
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, stream.readline)
            if not line:
                return
            try:
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            except Exception:
                text = repr(line)
            self._print(f"[{tag}] {text}")

    def _spawn(
        self,
        tag: str,
        argv: list[str],
        env: dict[str, str],
    ) -> subprocess.Popen[bytes]:
        """Spawn a child process with piped stdout/stderr.

        Children inherit the orchestrator's session/process group. Without
        ``start_new_session=True``, every fleet child, the admin UI server,
        the dashboard backend, and nats-server stay in the orchestrator's
        process group. That makes a single ``killpg(orch_pgid, SIGTERM)``
        from a parent (terminal Ctrl+C, integration test teardown,
        ``systemd-run --scope ...``, etc.) tear the whole tree down without
        relying on the orchestrator's asyncio loop being responsive: each
        child handles its own SIGTERM independently. The orchestrator's
        ``_shutdown()`` remains the correct path when the orchestrator
        decides to exit on its own (e.g. NATS death), but it is no longer
        the only path.

        T-02-09-03 mitigation: orphan dashboard/medevac/etc. processes are
        impossible because killpg reaches every leaf.
        """
        proc = subprocess.Popen(  # noqa: S603 -- argv is constructed from constants
            argv,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._log_tasks.append(asyncio.create_task(self._drain(tag, proc.stdout)))
        self._log_tasks.append(asyncio.create_task(self._drain(tag, proc.stderr)))
        return proc

    # ----------------------------------------------------------------- run loop

    async def run(self) -> int:
        """Boot, supervise, and clean up. Returns the orchestrator exit code."""
        self._install_signal_handlers()

        # 1. Resolve nats-server binary.
        binary = find_nats_server()
        if binary is None:
            self._print("[orchestrator] downloading nats-server ...")
            binary = await download_nats_server()

        # 2. Write HOCON config.
        store_dir = self.run_dir / f"jetstream-{self.nats_port}"
        self._config_path = write_nats_config(
            port=self.nats_port,
            ws_port=self.ws_port,
            http_port=self.http_port,
            store_dir=store_dir,
        )

        # 3. Spawn nats-server. Stays in the orchestrator's process group so
        # a parent ``killpg(orch_pgid, SIGTERM)`` reaps the entire tree
        # (see ``_spawn``); the orchestrator's own ``_shutdown`` still
        # SIGTERM-then-SIGKILL nats-server when it exits voluntarily.
        self._nats_proc = subprocess.Popen(  # noqa: S603 -- binary is a resolved Path
            [str(binary), "-c", str(self._config_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._log_tasks.append(
            asyncio.create_task(self._drain("nats", self._nats_proc.stdout))
        )
        self._log_tasks.append(
            asyncio.create_task(self._drain("nats", self._nats_proc.stderr))
        )

        # 4. Wait for NATS readiness on the standard port.
        try:
            await _wait_for_ready(self.nats_url, timeout=5.0)
        except RuntimeError:
            await self._shutdown()
            return 1

        self._print(
            f"[orchestrator] embedded NATS at {self.nats_url} "
            f"(ws on :{self.ws_port})"
        )

        # 5. Build child env.
        child_env = dict(os.environ)
        child_env["NATS_URL"] = self.nats_url

        # 6. Spawn fleet children.
        for logical_name, (module, count) in CHILD_SPECS.items():
            for idx in range(count):
                tag = f"{logical_name}-{idx}"
                proc = self._spawn(
                    tag,
                    [sys.executable, "-m", module],
                    child_env,
                )
                self._children[tag] = proc
                self._print(f"[orchestrator] spawned [{tag}] (pid={proc.pid})")

        # 7. Spawn oam ui (admin UI MVP, ADR-0056 amendment).
        # ``--port {ui_port}`` (default 8088) is the HTTP server port; it MUST
        # differ from ``--nats-ws-url`` (port 4223) to avoid colliding with the
        # NATS WebSocket listener. The ``ui`` subcommand is added to the CLI in
        # plan 08; spawning it through ``python -m openagentmesh.cli`` keeps
        # this orchestrator agnostic of the CLI's internals.
        self._ui_proc = self._spawn(
            "ui",
            [
                sys.executable,
                "-m",
                "openagentmesh.cli",
                "ui",
                "--port",
                str(self.ui_port),
                "--nats-ws-url",
                f"ws://127.0.0.1:{self.ws_port}",
            ],
            child_env,
        )
        self._print(f"[orchestrator] admin UI at http://127.0.0.1:{self.ui_port}")

        # 7b. Spawn scenario UI dashboard (D-37, D-39). The dashboard auto-falls
        # back to the next free port if ``dashboard_port`` is busy; this banner
        # prints the requested port. The resolved URL appears on [dash]-tagged
        # log lines so the viewer can recover the actual port if the fallback
        # kicked in.
        self._dash_proc = self._spawn(
            "dash",
            [
                sys.executable,
                "-m",
                "demos.wildfire.dashboard",
                "--port",
                str(self.dashboard_port),
            ],
            child_env,
        )
        self._print(
            f"[orchestrator] dashboard at http://127.0.0.1:{self.dashboard_port}"
        )
        self._print("[orchestrator] ready -- Ctrl+C to stop")

        # 8. Supervise.
        try:
            await self._supervise()
        finally:
            await self._shutdown()
        return 0

    # ----------------------------------------------------------------- signals

    def _install_signal_handlers(self) -> None:
        """Trap SIGINT/SIGTERM into ``self._stop``. Best-effort on Windows."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Windows lacks loop.add_signal_handler; fall back to
            # KeyboardInterrupt in __main__ on that platform.
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._stop.set)

    async def _supervise(self) -> None:
        """Wait until SIGINT/SIGTERM, NATS death, or all children dead.

        Per the no-restart policy, child exits are logged but not retried; the
        orchestrator only stops on signal or if NATS itself dies.
        """
        while not self._stop.is_set():
            # NATS death is fatal.
            if self._nats_proc is not None and self._nats_proc.poll() is not None:
                self._print(
                    f"[orchestrator] nats-server exited "
                    f"(code={self._nats_proc.returncode}); shutting down"
                )
                return
            # Track child deaths (log once, then forget so we don't spam).
            for tag, proc in list(self._children.items()):
                if proc.poll() is not None:
                    self._print(f"[{tag}] exited (code={proc.returncode})")
                    del self._children[tag]
            if self._ui_proc is not None and self._ui_proc.poll() is not None:
                self._print(f"[ui] exited (code={self._ui_proc.returncode})")
                self._ui_proc = None
            if self._dash_proc is not None and self._dash_proc.poll() is not None:
                self._print(f"[dash] exited (code={self._dash_proc.returncode})")
                self._dash_proc = None
            await asyncio.sleep(0.5)

    # ----------------------------------------------------------------- cleanup

    async def _shutdown(self) -> None:
        """Terminate every child, then NATS, then drop the temp config file.

        Children get 5 s to exit gracefully on SIGTERM before being SIGKILLed.
        """
        self._print("[orchestrator] stopping ...")

        # Children first (UI + dashboard + fleet).
        procs: list[subprocess.Popen[bytes]] = list(self._children.values())
        if self._ui_proc is not None:
            procs.append(self._ui_proc)
        if self._dash_proc is not None:
            procs.append(self._dash_proc)
        for proc in procs:
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
        await self._wait_or_kill(procs, timeout=5.0)

        # NATS last so children can flush KV writes through it before exit.
        if self._nats_proc is not None:
            with contextlib.suppress(ProcessLookupError):
                self._nats_proc.terminate()
            await self._wait_or_kill([self._nats_proc], timeout=5.0)
            self._nats_proc = None

        # Drain log forwarders so we don't lose final lines.
        for task in self._log_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                task.cancel()
        for task in self._log_tasks:
            with contextlib.suppress(BaseException):
                await task
        self._log_tasks.clear()

        # Drop temp HOCON config (T-01-03-01).
        if self._config_path is not None:
            with contextlib.suppress(FileNotFoundError):
                self._config_path.unlink()
            self._config_path = None

    @staticmethod
    async def _wait_or_kill(
        procs: list[subprocess.Popen[bytes]], *, timeout: float
    ) -> None:
        """Wait up to ``timeout`` seconds for ``procs`` to exit, then SIGKILL."""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        for proc in procs:
            remaining = max(0.0, deadline - loop.time())
            try:
                await loop.run_in_executor(None, lambda p=proc, r=remaining: p.wait(timeout=r))
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                with contextlib.suppress(BaseException):
                    await loop.run_in_executor(None, proc.wait)
