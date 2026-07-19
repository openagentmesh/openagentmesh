"""Tests for the admin UI cookbook recipe (docs/cookbook/admin-ui.md).

The recipe is operational (serve the UI, open a browser), so the executable
twin covers the CLI surface the recipe demonstrates: `oam ui --check`
resolving the WebSocket URL, and the remote-mesh override. The browser side
is covered by the smoke e2e (ui/e2e/smoke.mjs) against a real mesh.
"""

from typer.testing import CliRunner

from openagentmesh.cli import app

runner = CliRunner()


def _assets(tmp_path):
    (tmp_path / "index.html").write_text("<html>ui</html>")
    return tmp_path


class TestAdminUIRecipe:
    def test_check_derives_ws_url_from_mesh_url(self, tmp_path, monkeypatch):
        # Recipe: `oam ui --check` — WebSocket listener is mesh port + 1.
        monkeypatch.setenv("OAM_URL", "nats://localhost:4222")
        result = runner.invoke(app, ["ui", "--check", "--assets-dir", str(_assets(tmp_path))])
        assert result.exit_code == 0
        assert "ws://localhost:4223" in result.output

    def test_remote_mesh_override(self, tmp_path):
        # Recipe: OAM_URL=... oam ui --nats-ws-url wss://mesh.example.com:4223
        result = runner.invoke(
            app,
            [
                "ui",
                "--check",
                "--url",
                "nats://mesh.example.com:4222",
                "--nats-ws-url",
                "wss://mesh.example.com:4223",
                "--assets-dir",
                str(_assets(tmp_path)),
            ],
        )
        assert result.exit_code == 0
        assert "wss://mesh.example.com:4223" in result.output
