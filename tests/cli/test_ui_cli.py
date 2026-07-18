"""`oam ui` CLI surface (ADR-0056 wave 1)."""

from __future__ import annotations

from typer.testing import CliRunner

from openagentmesh.cli import app

runner = CliRunner()


def _make_assets(tmp_path):
    (tmp_path / "index.html").write_text("<html>ui</html>")
    return tmp_path


def test_ui_check_prints_resolved_urls(tmp_path, monkeypatch):
    assets = _make_assets(tmp_path)
    monkeypatch.setenv("OAM_URL", "nats://localhost:4222")
    result = runner.invoke(app, ["ui", "--check", "--assets-dir", str(assets)])
    assert result.exit_code == 0
    assert "ws://localhost:4223" in result.output


def test_ui_check_env_override_wins(tmp_path, monkeypatch):
    assets = _make_assets(tmp_path)
    monkeypatch.setenv("OAM_NATS_WS_URL", "wss://mesh.example.com:9999")
    result = runner.invoke(app, ["ui", "--check", "--assets-dir", str(assets)])
    assert result.exit_code == 0
    assert "wss://mesh.example.com:9999" in result.output


def test_ui_missing_assets_exits_with_guidance(tmp_path):
    result = runner.invoke(app, ["ui", "--check", "--assets-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "pnpm" in result.output
