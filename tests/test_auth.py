"""Auth tests for ADR-0038: creds resolution, JWT connect, connection_denied.

Runs a real nats-server in operator (NKey + JWT) mode using the static
credentials in tests/auth_fixtures/ (see its README). The SDK surface under
test is the ADR-0038 code sample:

    mesh = AgentMesh(url=..., creds="./worker.creds")
"""

import socket
import subprocess
import textwrap
import time
from pathlib import Path

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, ConnectionDenied, MeshError
from openagentmesh._local import _free_port, find_nats_server

FIXTURES = "tests/auth_fixtures"
ACCOUNT_PUBLIC_KEY = "ADY6WZ3PGJNK7G5VT2Z47GDMJVDFXXJ65BC3YEUFP7LGK7A3W3XBREDR"
SYS_ACCOUNT_PUBLIC_KEY = "ABT4SBY5ITUPXZRXVMNUDXV3Q3UDTNXYS7TKZHBIGV5A3YIUDHAQKXYL"


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    reply: str


@pytest.fixture(scope="module")
def auth_server(tmp_path_factory):
    """A JWT-auth'd nats-server with JetStream; yields its client URL."""
    binary = find_nats_server()
    assert binary is not None, "nats-server binary required (see roadmap-learnings)"

    tmp = tmp_path_factory.mktemp("nats-auth")
    fx = Path(FIXTURES).resolve()
    port = _free_port()
    account_jwt = (fx / "account-TEST.jwt").read_text().strip()
    sys_jwt = (fx / "account-SYS.jwt").read_text().strip()
    conf = tmp / "server.conf"
    conf.write_text(
        textwrap.dedent(f"""
        port: {port}
        operator: {fx}/operator.jwt
        system_account: {SYS_ACCOUNT_PUBLIC_KEY}
        resolver: MEMORY
        resolver_preload: {{
          {ACCOUNT_PUBLIC_KEY}: "{account_jwt}"
          {SYS_ACCOUNT_PUBLIC_KEY}: "{sys_jwt}"
        }}
        jetstream {{ store_dir: "{tmp}/js" }}
        """)
    )
    proc = subprocess.Popen(
        [str(binary), "-c", str(conf)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    url = f"nats://127.0.0.1:{port}"
    for _ in range(50):
        time.sleep(0.1)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(f"auth nats-server exited: {stderr}")
        # Readiness probe: TCP connect is enough (auth rejects NATS-level pings).
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            continue
    else:
        raise RuntimeError("auth nats-server did not become ready")

    yield url

    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
def worker_mesh(auth_server):
    return AgentMesh(url=auth_server, creds=f"{FIXTURES}/worker.creds")


# --- Connecting with credentials (ADR-0038 §7) ---


async def test_creds_connect_register_and_call(worker_mesh):
    """The ADR code sample: a credentialed mesh hosts and calls an agent."""

    @worker_mesh.agent(
        AgentSpec(name="echo-auth", description="Echoes back the message.")
    )
    async def echo(req: EchoInput) -> EchoOutput:
        return EchoOutput(reply=f"echo: {req.message}")

    async with worker_mesh:
        result = await worker_mesh.call("echo-auth", {"message": "hi"})
        assert result["reply"] == "echo: hi"


async def test_anonymous_connect_raises_connection_denied(auth_server):
    """No creds against an auth'd server -> ConnectionDenied, not a generic failure."""
    mesh = AgentMesh(url=auth_server)
    with pytest.raises(ConnectionDenied) as excinfo:
        async with mesh:
            pass
    assert excinfo.value.code == "connection_denied"


async def test_connection_denied_is_a_mesh_error(auth_server):
    mesh = AgentMesh(url=auth_server)
    with pytest.raises(MeshError):
        async with mesh:
            pass


async def test_missing_creds_file_raises_clear_error(auth_server):
    mesh = AgentMesh(url=auth_server, creds="./does-not-exist.creds")
    with pytest.raises(MeshError) as excinfo:
        async with mesh:
            pass
    assert "does-not-exist.creds" in excinfo.value.message


# --- Credential resolution order (ADR-0038 §7) ---


async def test_oam_creds_env_var(auth_server, monkeypatch):
    """OAM_CREDS is used when no explicit creds argument is given."""
    monkeypatch.setenv("OAM_CREDS", f"{FIXTURES}/worker.creds")
    mesh = AgentMesh(url=auth_server)
    async with mesh:
        assert (await mesh.catalog()) is not None


async def test_oam_url_toml_creds_field(auth_server, tmp_path, monkeypatch):
    """.oam-url as TOML: creds resolved relative to the file's directory."""
    creds_src = Path(FIXTURES).resolve() / "worker.creds"
    (tmp_path / "worker.creds").write_bytes(creds_src.read_bytes())
    (tmp_path / ".oam-url").write_text(
        f'url = "{auth_server}"\ncreds = "worker.creds"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OAM_CREDS", raising=False)
    mesh = AgentMesh(url=auth_server)
    async with mesh:
        assert (await mesh.catalog()) is not None


def test_explicit_creds_beats_env(monkeypatch, tmp_path):
    from openagentmesh._auth import resolve_creds

    monkeypatch.setenv("OAM_CREDS", "/env/path.creds")
    assert resolve_creds("/explicit/path.creds", cwd=tmp_path) == "/explicit/path.creds"


def test_env_beats_oam_url_file(monkeypatch, tmp_path):
    from openagentmesh._auth import resolve_creds

    (tmp_path / ".oam-url").write_text('url = "nats://x:4222"\ncreds = "file.creds"\n')
    monkeypatch.setenv("OAM_CREDS", "/env/path.creds")
    assert resolve_creds(None, cwd=tmp_path) == "/env/path.creds"


def test_oam_url_creds_relative_to_file(monkeypatch, tmp_path):
    from openagentmesh._auth import resolve_creds

    (tmp_path / ".oam-url").write_text('url = "nats://x:4222"\ncreds = "file.creds"\n')
    monkeypatch.delenv("OAM_CREDS", raising=False)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    resolved = resolve_creds(None, cwd=nested)
    assert resolved == str(tmp_path / "file.creds")


def test_no_creds_resolves_to_none(monkeypatch, tmp_path):
    from openagentmesh._auth import resolve_creds

    monkeypatch.delenv("OAM_CREDS", raising=False)
    assert resolve_creds(None, cwd=tmp_path) is None


# --- .oam-url TOML backwards compatibility (ADR-0038 §9 / ADR-0033) ---


def test_bare_url_file_still_resolves(tmp_path):
    from openagentmesh.cli._config import resolve_url

    (tmp_path / ".oam-url").write_text("nats://legacy:4222\n")
    assert resolve_url(None, cwd=tmp_path) == "nats://legacy:4222"


def test_toml_url_file_resolves(tmp_path):
    from openagentmesh.cli._config import resolve_url

    (tmp_path / ".oam-url").write_text('url = "nats://toml:4222"\ncreds = "x.creds"\n')
    assert resolve_url(None, cwd=tmp_path) == "nats://toml:4222"


# --- TLS parameter pass-through (ADR-0038 §7) ---


async def test_tls_params_forwarded(monkeypatch, tmp_path):
    """tls_ca/tls_cert/tls_key produce an SSLContext handed to nats.connect."""
    import ssl

    import openagentmesh._mesh as mesh_mod

    captured: dict = {}

    async def fake_connect(url, **kwargs):
        captured.update(kwargs, url=url)
        raise RuntimeError("stop here")

    monkeypatch.setattr(mesh_mod.nats, "connect", fake_connect)

    ca, cert, key = _self_signed_bundle(tmp_path)
    mesh = AgentMesh(
        url="nats://localhost:4222",
        tls_ca=str(ca),
        tls_cert=str(cert),
        tls_key=str(key),
    )
    with pytest.raises(MeshError):
        async with mesh:
            pass
    assert isinstance(captured.get("tls"), ssl.SSLContext)


def _self_signed_bundle(tmp_path):
    """Generate a throwaway CA + cert + key with openssl (test-only)."""
    ca_key = tmp_path / "ca.key"
    ca = tmp_path / "ca.pem"
    key = tmp_path / "client.key"
    csr = tmp_path / "client.csr"
    cert = tmp_path / "client.pem"
    run = lambda *a: subprocess.run(a, check=True, capture_output=True)  # noqa: E731
    run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(ca_key), "-out", str(ca), "-days", "1",
        "-subj", "/CN=test-ca")
    run("openssl", "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(csr), "-subj", "/CN=client")
    run("openssl", "x509", "-req", "-in", str(csr), "-CA", str(ca),
        "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(cert), "-days", "1")
    return ca, cert, key
