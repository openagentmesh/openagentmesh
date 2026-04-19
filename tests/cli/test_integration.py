"""End-to-end: register an agent in a local mesh, invoke via the CLI subprocess."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec

REPO_ROOT = Path(__file__).resolve().parents[2]


class EchoIn(BaseModel):
    text: str


class EchoOut(BaseModel):
    reply: str


def _run_cli(args: list[str], url: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "OAM_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "openagentmesh.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=15,
    )


@pytest.mark.asyncio
async def test_catalog_inspect_call_health_end_to_end():
    async with AgentMesh.local() as mesh:
        @mesh.agent(AgentSpec(name="echo", description="Echoes text"))
        async def echo(req: EchoIn) -> EchoOut:
            return EchoOut(reply=f"echo: {req.text}")

        await mesh._subscribe_pending()  # ensure registration visible

        catalog = await asyncio.to_thread(_run_cli, ["mesh", "catalog", "--json"], mesh._url)
        assert catalog.returncode == 0, catalog.stderr
        entries = json.loads(catalog.stdout)
        assert any(e["name"] == "echo" for e in entries)

        inspect = await asyncio.to_thread(
            _run_cli, ["agent", "contract", "echo"], mesh._url
        )
        assert inspect.returncode == 0, inspect.stderr
        contract = json.loads(inspect.stdout)
        assert contract["name"] == "echo"

        call_arg = await asyncio.to_thread(
            _run_cli, ["agent", "call", "echo", '{"text": "hi"}'], mesh._url
        )
        assert call_arg.returncode == 0, call_arg.stderr
        assert json.loads(call_arg.stdout) == {"reply": "echo: hi"}

        call_stdin = await asyncio.to_thread(
            _run_cli, ["agent", "call", "echo"], mesh._url, '{"text": "pipe"}'
        )
        assert call_stdin.returncode == 0, call_stdin.stderr
        assert json.loads(call_stdin.stdout) == {"reply": "echo: pipe"}
