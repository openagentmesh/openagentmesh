"""Tests for `oam demo` CLI command (ADR-0041)."""

from __future__ import annotations

import asyncio

import pytest
from typer.testing import CliRunner

from openagentmesh import AgentMesh
from openagentmesh.cli import app
from openagentmesh.demos import hello_world

runner = CliRunner()


class TestDemoModuleContract:
    """The hello_world demo module must expose a docstring and async main(mesh)."""

    def test_hello_world_has_docstring(self):
        assert hello_world.__doc__ is not None
        assert len(hello_world.__doc__.strip()) > 0

    def test_hello_world_has_async_main(self):
        assert hasattr(hello_world, "main")
        assert asyncio.iscoroutinefunction(hello_world.main)

    async def test_hello_world_runs_against_local_mesh(self):
        async with AgentMesh.local() as mesh:
            result = await hello_world.main(mesh)
            assert result is None


class TestDemoCommand:
    """oam demo runs the hello-world demo against a local mesh."""

    def test_demo_runs(self):
        result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0
