"""Executable twin of docs/cookbook/agent-liveness.md (ADR-0016/0040)."""

import asyncio
import subprocess
import sys
import time

import pytest
from pydantic import BaseModel

from openagentmesh import AgentDied, AgentMesh, AgentSpec, NotFound

pytestmark = pytest.mark.asyncio

# A primary agent that accepts a request and then hangs; killed mid-call by
# the test to simulate a crash while holding our request.
PRIMARY_HOST = """
import asyncio, sys
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

class TaskIn(BaseModel):
    text: str

class TaskOut(BaseModel):
    result: str

mesh = AgentMesh(sys.argv[1])

@mesh.agent(AgentSpec(name="worker.primary", description="hangs, then dies"))
async def primary(req: TaskIn) -> TaskOut:
    await asyncio.sleep(600)
    return TaskOut(result="never")

async def main():
    async with mesh:
        await asyncio.Event().wait()

asyncio.run(main())
"""


class TaskIn(BaseModel):
    text: str


class TaskOut(BaseModel):
    result: str


# --- recipe code (same as the doc) ---


async def call_resilient(mesh: AgentMesh, primary: str, fallback: str, payload):
    """Try the primary agent; fail over the moment it leaves the mesh."""
    try:
        return await mesh.call(primary, payload, timeout=30.0)
    except (AgentDied, NotFound):
        return await mesh.call(fallback, payload, timeout=30.0)


# --- tests ---


async def test_failover_when_primary_dies_mid_request():
    async with AgentMesh.local() as mesh:

        @mesh.agent(AgentSpec(name="worker.fallback", description="always up"))
        async def fallback(req: TaskIn) -> TaskOut:
            return TaskOut(result=f"fallback:{req.text}")

        host = subprocess.Popen(
            [sys.executable, "-c", PRIMARY_HOST, mesh.url],
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if any(e.name == "worker.primary" for e in await mesh.catalog()):
                    break
                await asyncio.sleep(0.1)

            async def _kill_soon():
                await asyncio.sleep(0.8)
                host.kill()

            killer = asyncio.create_task(_kill_soon())
            started = time.monotonic()
            result = await call_resilient(
                mesh, "worker.primary", "worker.fallback", TaskIn(text="job")
            )
            elapsed = time.monotonic() - started
            await killer

            assert result == {"result": "fallback:job"}
            assert elapsed < 10.0, f"failover took {elapsed:.1f}s"
        finally:
            if host.poll() is None:
                host.kill()
            host.wait()


async def test_failover_when_primary_never_existed():
    async with AgentMesh.local() as mesh:

        @mesh.agent(AgentSpec(name="worker.fallback", description="always up"))
        async def fallback(req: TaskIn) -> TaskOut:
            return TaskOut(result=f"fallback:{req.text}")

        result = await call_resilient(
            mesh, "worker.gone", "worker.fallback", TaskIn(text="job")
        )
        assert result == {"result": "fallback:job"}


async def test_watchdog_sees_both_reasons():
    async with AgentMesh.local() as mesh:
        seen: list[dict] = []

        async def watchdog():
            async for notice in mesh.subscribe(subject="mesh.death.>"):
                seen.append(notice)

        task = asyncio.create_task(watchdog())
        try:
            await asyncio.sleep(0.3)

            host = subprocess.Popen(
                [sys.executable, "-c", PRIMARY_HOST, mesh.url],
                start_new_session=True,
            )
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if any(e.name == "worker.primary" for e in await mesh.catalog()):
                    break
                await asyncio.sleep(0.1)
            host.kill()
            host.wait()

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not seen:
                await asyncio.sleep(0.1)
            assert [n["reason"] for n in seen] == ["disconnect"]
            assert seen[0]["agent"] == "worker.primary"
        finally:
            task.cancel()
