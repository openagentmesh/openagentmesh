"""CLI surface for ADR-0038: `oam mesh connect --creds` and `oam auth whoami`."""

from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from openagentmesh.cli import app
from openagentmesh.cli._config import OAM_URL_FILE, write_url_file

runner = CliRunner()

FIXTURES = Path("tests/auth_fixtures").resolve()


# --- oam mesh connect --creds (ADR-0038 §9) ---


def test_connect_with_creds_writes_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["mesh", "connect", "nats://remote:4222", "--creds", "./luca.creds"]
    )
    assert result.exit_code == 0
    content = (tmp_path / OAM_URL_FILE).read_text()
    assert 'url = "nats://remote:4222"' in content
    assert 'creds = "./luca.creds"' in content


def test_connect_without_creds_keeps_bare_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["mesh", "connect", "nats://remote:4222"])
    assert result.exit_code == 0
    assert (tmp_path / OAM_URL_FILE).read_text().strip() == "nats://remote:4222"


def test_write_url_file_with_creds(tmp_path):
    write_url_file("nats://x:4222", creds="a.creds", cwd=tmp_path)
    content = (tmp_path / OAM_URL_FILE).read_text()
    assert 'url = "nats://x:4222"' in content
    assert 'creds = "a.creds"' in content


def test_connect_toml_roundtrips_through_resolvers(tmp_path, monkeypatch):
    from openagentmesh._auth import resolve_creds
    from openagentmesh.cli._config import resolve_url

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OAM_URL", raising=False)
    monkeypatch.delenv("OAM_CREDS", raising=False)
    runner.invoke(app, ["mesh", "connect", "nats://remote:4222", "--creds", "w.creds"])
    assert resolve_url(None, cwd=tmp_path) == "nats://remote:4222"
    assert resolve_creds(None, cwd=tmp_path) == str(tmp_path / "w.creds")


# --- oam auth whoami (ADR-0038 §9) ---


def test_whoami_reports_user_from_creds(tmp_path, monkeypatch):
    shutil.copy(FIXTURES / "worker.creds", tmp_path / "worker.creds")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OAM_CREDS", raising=False)
    runner.invoke(app, ["mesh", "connect", "nats://remote:4222", "--creds", "worker.creds"])
    result = runner.invoke(app, ["auth", "whoami"])
    assert result.exit_code == 0
    assert "worker" in result.stdout
    # the user's public NKey (sub claim of the user JWT)
    assert "UBGIT7A6OYCH2BTC6SQRA3QUXBGFNVFCDZ6IYLTNM7ANHVHEW75PQZUF" in result.stdout


def test_whoami_with_explicit_creds_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OAM_CREDS", raising=False)
    result = runner.invoke(
        app, ["auth", "whoami", "--creds", str(FIXTURES / "worker.creds")]
    )
    assert result.exit_code == 0
    assert "worker" in result.stdout


def test_whoami_without_creds_reports_open(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OAM_CREDS", raising=False)
    result = runner.invoke(app, ["auth", "whoami"])
    assert result.exit_code == 0
    assert "no credentials" in result.stdout.lower()


def test_whoami_missing_creds_file_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["auth", "whoami", "--creds", "nope.creds"])
    assert result.exit_code != 0
