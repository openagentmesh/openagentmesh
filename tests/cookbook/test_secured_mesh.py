"""Executable twin of docs/cookbook/secured-mesh.md (ADR-0038).

Same flow as the recipe: `oam auth init`, one credential per role, a server
booted from the emitted config, then worker/invoker/observer processes with
their distinct privileges. Wrapped in fixtures; the mesh-facing code matches
the recipe.
"""

from __future__ import annotations

import re
import socket
import subprocess
import time

import pytest
from pydantic import BaseModel
from typer.testing import CliRunner

from openagentmesh import AgentMesh, AgentSpec, ConnectionDenied
from openagentmesh._local import _free_port, find_nats_server
from openagentmesh.cli import app
from openagentmesh.cli.auth import find_nsc

runner = CliRunner()

pytestmark = pytest.mark.skipif(find_nsc() is None, reason="nsc binary not available")


class ScoreRequest(BaseModel):
    trade_id: str


class ScoreReply(BaseModel):
    risk: float


@pytest.fixture(scope="module")
def secured_mesh_url(tmp_path_factory):
    """`oam auth init` + three role credentials + a server from the config."""
    base = tmp_path_factory.mktemp("secured-mesh")
    oam = base / ".oam"
    r = runner.invoke(app, ["auth", "init", "--name", "mymesh", "--dir", str(oam)])
    assert r.exit_code == 0, r.output
    for name, role in [("pipeline", "worker"), ("caller", "invoker"), ("viewer", "observer")]:
        r = runner.invoke(
            app,
            ["auth", "user", "add", name, "--role", role,
             "--dir", str(oam), "--out", str(base / f"{name}.creds")],
        )
        assert r.exit_code == 0, r.output

    binary = find_nats_server()
    assert binary is not None
    port = _free_port()
    conf = base / "server.conf"
    conf.write_text(
        re.sub(
            r'jetstream \{ store_dir: "[^"]*" \}',
            f'jetstream {{ store_dir: "{base}/js" }}',
            (oam / "server.conf").read_text(),
        )
    )
    proc = subprocess.Popen(
        [str(binary), "-c", str(conf), "-p", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    for _ in range(50):
        time.sleep(0.1)
        if proc.poll() is not None:
            raise RuntimeError(proc.stderr.read().decode() if proc.stderr else "server died")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            continue

    yield f"nats://127.0.0.1:{port}", base

    proc.terminate()
    proc.wait(timeout=5)


async def test_worker_invoker_observer_roles(secured_mesh_url):
    url, base = secured_mesh_url

    # The worker: hosts an agent — auth is one constructor argument.
    worker = AgentMesh(url=url, creds=str(base / "pipeline.creds"))

    @worker.agent(AgentSpec(name="scorer", description="Scores risk for trades."))
    async def scorer(req: ScoreRequest) -> ScoreReply:
        return ScoreReply(risk=0.17 if req.trade_id else 1.0)

    async with worker:
        # The invoker: calls across processes.
        invoker = AgentMesh(url=url, creds=str(base / "caller.creds"))
        async with invoker:
            result = await invoker.call("scorer", {"trade_id": "t-17"})
            assert result["risk"] == 0.17

        # The observer: watch, but don't touch.
        observer = AgentMesh(url=url, creds=str(base / "viewer.creds"))
        async with observer:
            names = [entry.name for entry in await observer.catalog()]
            assert "scorer" in names

            with pytest.raises(ConnectionDenied):
                await observer.call("scorer", {"trade_id": "t-17"}, timeout=2.0)


async def test_no_credentials_is_denied(secured_mesh_url):
    url, _base = secured_mesh_url
    with pytest.raises(ConnectionDenied):
        async with AgentMesh(url=url):
            pass
