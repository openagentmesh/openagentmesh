"""Tests for `oam demo` CLI subcommand and demo module contract (ADR-0041)."""

from __future__ import annotations

import asyncio
import importlib

import pytest
from typer.testing import CliRunner

from openagentmesh import AgentMesh
from openagentmesh.cli import app
from openagentmesh.demos import hello_world

runner = CliRunner()


class TestDemoModuleContract:
    """Each demo module must expose a docstring and async main(mesh)."""

    def test_hello_world_has_docstring(self):
        assert hello_world.__doc__ is not None
        assert len(hello_world.__doc__.strip()) > 0

    def test_hello_world_has_async_main(self):
        assert hasattr(hello_world, "main")
        assert asyncio.iscoroutinefunction(hello_world.main)

    async def test_hello_world_runs_against_local_mesh(self):
        async with AgentMesh.local() as mesh:
            result = await hello_world.main(mesh)
            assert result is None  # main returns None; side effects are the point


class TestDemoList:
    """oam demo list shows available demos."""

    def test_list_shows_hello_world(self):
        result = runner.invoke(app, ["demo", "list"])
        assert result.exit_code == 0
        assert "hello_world" in result.output

    def test_list_shows_descriptions(self):
        result = runner.invoke(app, ["demo", "list"])
        assert result.exit_code == 0
        # Should show the module docstring as description
        assert hello_world.__doc__.strip().split("\n")[0] in result.output


class TestDemoShow:
    """oam demo show prints the source code."""

    def test_show_prints_source(self):
        result = runner.invoke(app, ["demo", "show", "hello_world"])
        assert result.exit_code == 0
        assert "async def main" in result.output
        assert "mesh" in result.output

    def test_show_unknown_demo_fails(self):
        result = runner.invoke(app, ["demo", "show", "nonexistent_demo"])
        assert result.exit_code != 0


class TestDemoRun:
    """oam demo run executes a demo against a local mesh."""

    def test_run_hello_world(self):
        result = runner.invoke(app, ["demo", "run", "hello_world"])
        assert result.exit_code == 0

    def test_run_unknown_demo_fails(self):
        result = runner.invoke(app, ["demo", "run", "nonexistent_demo"])
        assert result.exit_code != 0
