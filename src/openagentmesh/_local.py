"""Embedded NATS server for tests and demos (ADR-0022, ADR-0015)."""

from __future__ import annotations

import asyncio
import platform
import shutil
import socket
import stat
import subprocess
from pathlib import Path

import nats

NATS_VERSION = "2.10.24"
AGENTMESH_DIR = Path.home() / ".agentmesh"
NATS_BIN_DIR = AGENTMESH_DIR / "bin"


def _nats_binary_name() -> str:
    return "nats-server.exe" if platform.system() == "Windows" else "nats-server"


def find_nats_server() -> Path | None:
    """Find nats-server: prefer PATH, fall back to ~/.agentmesh/bin/ (ADR-0015)."""
    path_binary = shutil.which("nats-server")
    if path_binary:
        return Path(path_binary)

    local_binary = NATS_BIN_DIR / _nats_binary_name()
    if local_binary.exists():
        return local_binary

    return None


async def download_nats_server() -> Path:
    """Download nats-server binary to ~/.agentmesh/bin/."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    os_map = {"darwin": "darwin", "linux": "linux", "windows": "windows"}
    arch_map = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}

    os_name = os_map.get(system)
    arch_name = arch_map.get(machine)
    if not os_name or not arch_name:
        raise RuntimeError(f"Unsupported platform: {system}/{machine}")

    ext = "zip" if system == "windows" else "tar.gz"
    filename = f"nats-server-v{NATS_VERSION}-{os_name}-{arch_name}"
    url = (
        f"https://github.com/nats-io/nats-server/releases/download/"
        f"v{NATS_VERSION}/{filename}.{ext}"
    )

    NATS_BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = NATS_BIN_DIR / _nats_binary_name()

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / f"nats-server.{ext}"

        proc = await asyncio.create_subprocess_exec(
            "curl", "-fsSL", "-o", str(archive_path), url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to download nats-server: {stderr.decode()}")

        if ext == "tar.gz":
            proc = await asyncio.create_subprocess_exec(
                "tar", "xzf", str(archive_path), "-C", tmpdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        else:
            import zipfile

            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(tmpdir)

        extracted_binary = Path(tmpdir) / filename / _nats_binary_name()
        if not extracted_binary.exists():
            raise RuntimeError(f"nats-server binary not found in archive at {extracted_binary}")

        shutil.copy2(extracted_binary, target)
        target.chmod(target.stat().st_mode | stat.S_IEXEC)

    return target


def _free_port() -> int:
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# HOCON template for the embedded NATS server.
#
# Both the standard listener and the WebSocket listener bind to ``127.0.0.1``
# only. This is the Phase 1 threat-model default per ADR-0056 amendment: the
# admin UI assumes localhost-only deployments; remote auth is gated by a
# future enterprise ADR. The template mirrors the orchestrator helper in
# ``demos/wildfire/core/nats_config.py`` but is intentionally inlined here so
# the SDK does not import anything from ``demos.*`` (D-00 / amendment SDK side).
_HOCON_TEMPLATE = """\
host: "127.0.0.1"
port: {port}
jetstream {{
    store_dir: "{store_dir}"
}}
websocket {{
    host: "127.0.0.1"
    port: {ws_port}
    no_tls: true
}}
"""


def _write_nats_config(*, port: int, ws_port: int, store_dir: Path) -> Path:
    """Write a HOCON NATS config file under ``store_dir`` and return its path.

    The config enables both the standard listener and a WebSocket listener,
    each bound to ``127.0.0.1``. Quotes inside ``store_dir`` are escaped so
    paths with embedded ``"`` characters don't break HOCON parsing.
    """
    store_dir.mkdir(parents=True, exist_ok=True)
    config_path = store_dir / "nats.conf"
    body = _HOCON_TEMPLATE.format(
        port=port,
        ws_port=ws_port,
        store_dir=str(store_dir).replace('"', '\\"'),
    )
    config_path.write_text(body)
    return config_path


class EmbeddedNats:
    """Manages an embedded NATS server subprocess with JetStream."""

    def __init__(self, port: int = 0) -> None:
        self.port: int = port
        self.url: str = ""
        self.ws_port: int = 0
        self.ws_url: str = ""
        self._process: subprocess.Popen | None = None
        self._data_dir: Path | None = None
        self._config_path: Path | None = None

    async def start(self) -> None:
        binary = find_nats_server()
        if not binary:
            binary = await download_nats_server()

        if self.port == 0:
            self.port = _free_port()
        # WebSocket listener always gets its own free port, independent of the
        # standard listener choice (ADR-0056 amendment: browser <-> NATS).
        self.ws_port = _free_port()
        self.url = f"nats://127.0.0.1:{self.port}"
        self.ws_url = f"ws://127.0.0.1:{self.ws_port}"
        self._data_dir = AGENTMESH_DIR / "data" / f"embedded-{self.port}"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._config_path = _write_nats_config(
            port=self.port,
            ws_port=self.ws_port,
            store_dir=self._data_dir,
        )

        self._process = subprocess.Popen(
            [str(binary), "-c", str(self._config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        # Wait for server readiness
        for _ in range(50):
            await asyncio.sleep(0.1)
            if self._process.poll() is not None:
                stderr = self._process.stderr.read().decode() if self._process.stderr else ""
                raise RuntimeError(f"NATS server exited unexpectedly: {stderr}")
            try:
                nc = await nats.connect(self.url)
                await nc.close()
                print(f"[openagentmesh] embedded NATS at {self.url} (ws on {self.ws_url})")
                return
            except Exception:
                continue

        raise RuntimeError("NATS server did not become ready in 5 seconds")

    async def stop(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None

        if self._data_dir and self._data_dir.exists():
            shutil.rmtree(self._data_dir, ignore_errors=True)
