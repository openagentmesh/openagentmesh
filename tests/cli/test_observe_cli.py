"""`oam observe` CLI (ADR-0048 v1): config, set, and logs tail."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec

REPO_ROOT = Path(__file__).resolve().parents[2]


class In(BaseModel):
    text: str


class Out(BaseModel):
    reply: str


def _run_cli(args: list[str], url: str, timeout: float = 15) -> subprocess.CompletedProcess:
    env = {**os.environ, "OAM_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "openagentmesh.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.mark.asyncio
async def test_observe_set_and_config_roundtrip():
    async with AgentMesh.local() as mesh:
        set_agent = await asyncio.to_thread(
            _run_cli,
            ["observe", "set", "nlp.summarizer", "--log-level", "debug"],
            mesh.url,
        )
        assert set_agent.returncode == 0, set_agent.stderr

        set_global = await asyncio.to_thread(
            _run_cli, ["observe", "set", "--global", "--log-level", "warn"], mesh.url
        )
        assert set_global.returncode == 0, set_global.stderr

        config = await asyncio.to_thread(
            _run_cli, ["observe", "config", "--json"], mesh.url
        )
        assert config.returncode == 0, config.stderr
        parsed = json.loads(config.stdout)
        assert parsed["global"]["log_level"] == "warn"
        assert parsed["agents"]["nlp.summarizer"]["log_level"] == "debug"

        single = await asyncio.to_thread(
            _run_cli, ["observe", "config", "nlp.summarizer", "--json"], mesh.url
        )
        assert single.returncode == 0, single.stderr
        parsed_single = json.loads(single.stdout)
        assert parsed_single["log_level"] == "debug"
        assert parsed_single["source"] == "agent"


@pytest.mark.asyncio
async def test_observe_logs_tails_events():
    async with AgentMesh.local() as mesh:
        @mesh.agent(AgentSpec(name="tail.agent", description="Tail target"))
        async def handler(req: In) -> Out:
            raise ValueError("boom")

        await mesh._subscribe_pending()

        env = {**os.environ, "OAM_URL": mesh.url}
        proc = subprocess.Popen(
            [sys.executable, "-m", "openagentmesh.cli", "observe", "logs", "tail.agent"],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            await asyncio.sleep(1.5)  # let the tail subscribe

            for _ in range(3):
                with contextlib.suppress(Exception):
                    await mesh.call("tail.agent", {"text": "x"})
                await asyncio.sleep(0.2)

            await asyncio.sleep(0.5)
        finally:
            proc.terminate()
            out, err = proc.communicate(timeout=10)

        assert "request_failed" in out, f"stdout: {out!r}\nstderr: {err!r}"
        assert "tail.agent" in out
