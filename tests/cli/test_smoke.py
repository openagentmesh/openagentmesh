from typer.testing import CliRunner

from openagentmesh.cli import app

runner = CliRunner()


def test_root_help_lists_binary_name():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "oam" in result.stdout.lower()


def test_root_without_args_shows_help():
    result = runner.invoke(app, [])
    assert result.exit_code != 0 or "Usage" in result.stdout
