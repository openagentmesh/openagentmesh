"""Embedded NATS server for tests and demos (ADR-0022, ADR-0015)."""

from __future__ import annotations

import asyncio
import platform
import secrets
import shutil
import socket
import stat
import subprocess
import textwrap
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


def render_mesh_server_conf(
    *, port: int, store_dir: Path, sys_password: str
) -> str:
    """NATS config for a dev mesh (ADR-0016).

    Anonymous clients map to the APP account (JetStream enabled) via
    ``no_auth_user``, preserving the open-by-default local DX. The SYS
    account exists so the health monitor can subscribe to ``$SYS.>``
    disconnect advisories. Ping settings follow the liveness spec (§5.2):
    partitions are detected in ~20s instead of NATS's ~4min default.
    """
    return textwrap.dedent(f"""
        port: {port}
        jetstream {{ store_dir: "{store_dir}" }}
        accounts {{
          APP: {{
            jetstream: enabled
            users: [ {{ user: "oam-app", password: "{sys_password}" }} ]
          }}
          SYS: {{
            users: [ {{ user: "oam-sys", password: "{sys_password}" }} ]
          }}
        }}
        no_auth_user: "oam-app"
        system_account: SYS
        ping_interval: "10s"
        ping_max: 2
        """)


class EmbeddedNats:
    """Manages an embedded NATS server subprocess with JetStream."""

    def __init__(self, port: int = 0) -> None:
        self.port: int = port
        self.url: str = ""
        self.sys_url: str = ""  # system-account URL for the health monitor
        self._process: subprocess.Popen | None = None
        self._data_dir: Path | None = None

    async def start(self) -> None:
        binary = find_nats_server()
        if not binary:
            binary = await download_nats_server()

        if self.port == 0:
            self.port = _free_port()
        sys_password = secrets.token_hex(16)
        self.url = f"nats://127.0.0.1:{self.port}"
        self.sys_url = f"nats://oam-sys:{sys_password}@127.0.0.1:{self.port}"
        self._data_dir = AGENTMESH_DIR / "data" / f"embedded-{self.port}"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        conf_path = self._data_dir / "nats.conf"
        conf_path.write_text(
            render_mesh_server_conf(
                port=self.port, store_dir=self._data_dir, sys_password=sys_password
            )
        )
        conf_path.chmod(0o600)

        self._process = subprocess.Popen(
            [str(binary), "-c", str(conf_path)],
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
                print(f"[openagentmesh] embedded NATS at {self.url}")
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
