"""End-to-end tests for `oam auth init` / `user add` / `user revoke` (ADR-0038).

These wrap nsc, so they need the nsc binary (PATH or ~/.agentmesh/bin) and a
real nats-server. The flow under test is the ADR §4 code sample: init a
credential tree, add role-templated users, boot a server from the emitted
config, and drive a real AgentMesh through it.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest
from pydantic import BaseModel
from typer.testing import CliRunner

from openagentmesh import AgentMesh, AgentSpec, ConnectionDenied
from openagentmesh._local import _free_port, find_nats_server
from openagentmesh.cli import app
from openagentmesh.cli.auth import find_nsc

runner = CliRunner()

pytestmark = pytest.mark.skipif(find_nsc() is None, reason="nsc binary not available")


def _boot_server(conf: Path, port: int, store_dir: Path) -> subprocess.Popen:
    binary = find_nats_server()
    assert binary is not None
    # per-boot copy with its own JetStream store so parallel servers don't collide
    import re

    content = re.sub(
        r'jetstream \{ store_dir: "[^"]*" \}',
        f'jetstream {{ store_dir: "{store_dir}/js" }}',
        conf.read_text(),
    )
    boot_conf = store_dir / "server.conf"
    boot_conf.write_text(content)
    proc = subprocess.Popen(
        [str(binary), "-c", str(boot_conf), "-p", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    import socket

    for _ in range(50):
        time.sleep(0.1)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(f"nats-server exited: {stderr}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return proc
        except OSError:
            continue
    raise RuntimeError("nats-server did not become ready")


@pytest.fixture(scope="module")
def authdir(tmp_path_factory):
    """`oam auth init` plus one user of each role, in an isolated directory."""
    base = tmp_path_factory.mktemp("auth-init")
    r = runner.invoke(
        app,
        ["auth", "init", "--name", "testmesh", "--dir", str(base / ".oam")],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    for name, role in [("pipeline", "worker"), ("caller", "invoker"), ("viewer", "observer")]:
        r = runner.invoke(
            app,
            [
                "auth", "user", "add", name,
                "--role", role,
                "--dir", str(base / ".oam"),
                "--out", str(base / f"{name}.creds"),
            ],
            catch_exceptions=False,
        )
        assert r.exit_code == 0, r.output
        assert (base / f"{name}.creds").is_file()
    return base


@pytest.fixture(scope="module")
def secured_url(authdir, tmp_path_factory):
    port = _free_port()
    store = tmp_path_factory.mktemp("js-store")
    proc = _boot_server(authdir / ".oam" / "server.conf", port, store)
    yield f"nats://127.0.0.1:{port}", authdir
    proc.terminate()
    proc.wait(timeout=5)


class EchoIn(BaseModel):
    message: str


class EchoOut(BaseModel):
    reply: str


def test_init_writes_config_and_store(authdir):
    oam = authdir / ".oam"
    conf = (oam / "server.conf").read_text()
    assert "operator:" in conf
    assert "resolver: MEMORY" in conf
    assert "system_account:" in conf
    assert (oam / "auth.toml").is_file()


async def test_worker_hosts_and_calls(secured_url):
    url, base = secured_url
    mesh = AgentMesh(url=url, creds=str(base / "pipeline.creds"))

    @mesh.agent(AgentSpec(name="echo-secured", description="Echoes."))
    async def echo(req: EchoIn) -> EchoOut:
        return EchoOut(reply=f"echo: {req.message}")

    async with mesh:
        result = await mesh.call("echo-secured", {"message": "hi"})
        assert result["reply"] == "echo: hi"


async def test_invoker_calls_worker_agent(secured_url):
    url, base = secured_url
    host = AgentMesh(url=url, creds=str(base / "pipeline.creds"))

    @host.agent(AgentSpec(name="echo-x", description="Echoes."))
    async def echo(req: EchoIn) -> EchoOut:
        return EchoOut(reply=f"echo: {req.message}")

    async with host:
        invoker = AgentMesh(url=url, creds=str(base / "caller.creds"))
        async with invoker:
            result = await invoker.call("echo-x", {"message": "cross"})
            assert result["reply"] == "echo: cross"


async def test_observer_reads_catalog_but_cannot_invoke(secured_url):
    url, base = secured_url
    host = AgentMesh(url=url, creds=str(base / "pipeline.creds"))

    @host.agent(AgentSpec(name="echo-o", description="Echoes."))
    async def echo(req: EchoIn) -> EchoOut:
        return EchoOut(reply=f"echo: {req.message}")

    async with host:
        observer = AgentMesh(url=url, creds=str(base / "viewer.creds"))
        async with observer:
            names = [e.name for e in await observer.catalog()]
            assert "echo-o" in names
            # publish on mesh.agent.> is denied; the async violation report
            # turns the resulting timeout into ConnectionDenied (ADR-0038)
            with pytest.raises(ConnectionDenied):
                await observer.call("echo-o", {"message": "nope"}, timeout=1.0)


def test_user_revoke_locks_user_out(authdir, tmp_path_factory):
    r = runner.invoke(
        app,
        ["auth", "user", "revoke", "pipeline", "--dir", str(authdir / ".oam")],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output

    # revocation lands in the account JWT; the regenerated config must be
    # reloaded, so boot a fresh server from it
    port = _free_port()
    store = tmp_path_factory.mktemp("js-revoked")
    proc = _boot_server(authdir / ".oam" / "server.conf", port, store)
    try:
        url = f"nats://127.0.0.1:{port}"

        async def _attempt(creds: str):
            async with AgentMesh(url=url, creds=creds):
                pass

        import asyncio

        with pytest.raises(ConnectionDenied):
            asyncio.run(_attempt(str(authdir / "pipeline.creds")))
        # non-revoked user still connects
        asyncio.run(_attempt(str(authdir / "caller.creds")))
    finally:
        proc.terminate()
        proc.wait(timeout=5)
