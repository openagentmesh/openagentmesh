"""Liveness tests for ADR-0016 (disconnect advisories, death notices) and
ADR-0040 (death-notice fast-fail for in-flight requests).

Agent hosts run as real subprocesses so SIGKILL genuinely severs the TCP
connection: the embedded server's health monitor must observe the disconnect
advisory, clean the catalog/registry, and publish `mesh.death.{name}`.
"""

import asyncio
import json
import subprocess
import sys
import time

import pytest

from openagentmesh import AgentMesh
from openagentmesh._errors import AgentDied, MeshTimeout, NotFound

pytestmark = pytest.mark.asyncio

HOST_SCRIPT = """
import asyncio, sys
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

url, name, mode = sys.argv[1], sys.argv[2], sys.argv[3]

class In(BaseModel):
    message: str

class Out(BaseModel):
    reply: str

mesh = AgentMesh(url)

if mode == "echo":
    @mesh.agent(AgentSpec(name=name, description="test victim"))
    async def victim(req: In) -> Out:
        return Out(reply=req.message)
elif mode == "hang":
    @mesh.agent(AgentSpec(name=name, description="accepts then hangs"))
    async def victim(req: In) -> Out:
        await asyncio.sleep(600)
        return Out(reply="too late")
elif mode == "stream_hang":
    @mesh.agent(AgentSpec(name=name, description="streams one chunk then hangs"))
    async def victim(req: In) -> Out:
        yield Out(reply="chunk0")
        await asyncio.sleep(600)

async def main():
    async with mesh:
        print("READY", flush=True)
        await asyncio.Event().wait()

asyncio.run(main())
"""


def _spawn_host(url: str, name: str, mode: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", HOST_SCRIPT, url, name, mode],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


async def _wait_registered(mesh: AgentMesh, name: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entries = await mesh.catalog()
        if any(e.name == name for e in entries):
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"agent {name!r} never appeared in the catalog")


async def _wait_deregistered(mesh: AgentMesh, name: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entries = await mesh.catalog()
        if not any(e.name == name for e in entries):
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"agent {name!r} still in the catalog after {timeout}s")


def _death_collector(mesh: AgentMesh) -> tuple[asyncio.Task, asyncio.Queue]:
    """Subscribe to mesh.death.> and collect notices into a queue."""
    notices: asyncio.Queue = asyncio.Queue()

    async def _collect() -> None:
        async for notice in mesh.subscribe(subject="mesh.death.>"):
            await notices.put(notice)

    return asyncio.create_task(_collect()), notices


class _HostGuard:
    """Ensure subprocess hosts are killed even when a test fails."""

    def __init__(self) -> None:
        self.procs: list[subprocess.Popen] = []

    def spawn(self, url: str, name: str, mode: str) -> subprocess.Popen:
        proc = _spawn_host(url, name, mode)
        self.procs.append(proc)
        return proc

    def cleanup(self) -> None:
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
            proc.wait()


@pytest.fixture
def hosts():
    guard = _HostGuard()
    yield guard
    guard.cleanup()


# --- ADR-0016: disconnect advisories and death notices ---


async def test_sigkill_publishes_death_notice_and_cleans_catalog(hosts):
    async with AgentMesh.local() as mesh:
        host = hosts.spawn(mesh.url, "victim.crash", "echo")
        await _wait_registered(mesh, "victim.crash")

        collector, notices = _death_collector(mesh)
        try:
            await asyncio.sleep(0.3)  # let the death subscription settle
            host.kill()  # SIGKILL: no graceful deregistration possible

            notice = await asyncio.wait_for(notices.get(), timeout=5.0)
            assert notice["agent"] == "victim.crash"
            assert notice["reason"] == "disconnect"

            # The ADR-0016 promise: catalog accuracy, not 30s staleness.
            await _wait_deregistered(mesh, "victim.crash", timeout=5.0)
        finally:
            collector.cancel()


async def test_graceful_shutdown_publishes_death_notice():
    async with AgentMesh.local() as watcher:
        collector, notices = _death_collector(watcher)
        try:
            await asyncio.sleep(0.3)

            from pydantic import BaseModel

            from openagentmesh import AgentSpec

            class In(BaseModel):
                message: str

            class Out(BaseModel):
                reply: str

            host = AgentMesh(watcher.url)

            @host.agent(AgentSpec(name="victim.graceful", description="exits cleanly"))
            async def victim(req: In) -> Out:  # pragma: no cover - never invoked
                return Out(reply=req.message)

            async with host:
                await _wait_registered(watcher, "victim.graceful")

            notice = await asyncio.wait_for(notices.get(), timeout=5.0)
            assert notice["agent"] == "victim.graceful"
            assert notice["reason"] == "graceful_shutdown"
            await _wait_deregistered(watcher, "victim.graceful", timeout=5.0)
        finally:
            collector.cancel()


async def test_scale_down_of_one_replica_is_not_a_death(hosts):
    """Death notices fire only when the LAST instance disconnects (ADR-0016)."""
    async with AgentMesh.local() as mesh:
        host_a = hosts.spawn(mesh.url, "victim.replicated", "echo")
        host_b = hosts.spawn(mesh.url, "victim.replicated", "echo")
        await _wait_registered(mesh, "victim.replicated")
        # Both hosts must be fully up before we start killing.
        for proc in (host_a, host_b):
            assert proc.poll() is None
        await asyncio.sleep(1.0)  # let both instance records land

        collector, notices = _death_collector(mesh)
        try:
            await asyncio.sleep(0.3)
            host_a.kill()

            # One replica down: no death notice, agent stays in the catalog.
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(notices.get(), timeout=2.0)
            entries = await mesh.catalog()
            assert any(e.name == "victim.replicated" for e in entries)

            host_b.kill()
            notice = await asyncio.wait_for(notices.get(), timeout=5.0)
            assert notice["agent"] == "victim.replicated"
            assert notice["reason"] == "disconnect"
            await _wait_deregistered(mesh, "victim.replicated", timeout=5.0)
        finally:
            collector.cancel()


# --- ADR-0040: fast-fail for in-flight requests ---


async def test_call_fast_fails_when_agent_dies_mid_request(hosts):
    """The chaos test (stage exit criterion): kill an agent mid-request and
    assert the caller gets `agent_died` sub-timeout instead of MeshTimeout."""
    async with AgentMesh.local() as mesh:
        host = hosts.spawn(mesh.url, "victim.hang", "hang")
        await _wait_registered(mesh, "victim.hang")

        async def _kill_soon() -> None:
            await asyncio.sleep(0.8)  # let the request reach the handler
            host.kill()

        killer = asyncio.create_task(_kill_soon())
        started = time.monotonic()
        with pytest.raises(AgentDied) as exc_info:
            await mesh.call("victim.hang", {"message": "hi"}, timeout=30.0)
        elapsed = time.monotonic() - started
        await killer

        assert exc_info.value.code == "agent_died"
        assert exc_info.value.agent == "victim.hang"
        # Sub-second detection plus test overhead: must beat the 30s timeout
        # by a wide margin, or fast-fail is not happening.
        assert elapsed < 10.0, f"fast-fail took {elapsed:.1f}s"


async def test_stream_fast_fails_when_agent_dies_mid_stream(hosts):
    async with AgentMesh.local() as mesh:
        host = hosts.spawn(mesh.url, "victim.streamhang", "stream_hang")
        await _wait_registered(mesh, "victim.streamhang")

        started = time.monotonic()
        with pytest.raises(AgentDied):
            chunks = []
            async for chunk in mesh.stream(
                "victim.streamhang", {"message": "hi"}, timeout=30.0
            ):
                chunks.append(chunk)
                host.kill()  # kill after the first chunk arrives
        elapsed = time.monotonic() - started
        assert chunks == [{"reply": "chunk0"}]
        assert elapsed < 10.0, f"fast-fail took {elapsed:.1f}s"


async def test_call_to_absent_agent_raises_not_found():
    """`no responders` maps to NotFound, not a raw NATS error (ADR-0040)."""
    async with AgentMesh.local() as mesh:
        started = time.monotonic()
        with pytest.raises(NotFound):
            await mesh.call("ghost.agent", {"message": "hi"}, timeout=10.0)
        # No-responders is an immediate broker signal, not a timeout.
        assert time.monotonic() - started < 5.0


async def test_timeout_still_raised_when_agent_alive_but_slow(hosts):
    """A hung-but-alive agent is a zombie: callers still get MeshTimeout."""
    async with AgentMesh.local() as mesh:
        hosts.spawn(mesh.url, "victim.slow", "hang")
        await _wait_registered(mesh, "victim.slow")
        with pytest.raises(MeshTimeout):
            await mesh.call("victim.slow", {"message": "hi"}, timeout=1.0)


async def test_death_notice_payload_shape(hosts):
    async with AgentMesh.local() as mesh:
        host = hosts.spawn(mesh.url, "victim.payload", "echo")
        await _wait_registered(mesh, "victim.payload")
        collector, notices = _death_collector(mesh)
        try:
            await asyncio.sleep(0.3)
            host.kill()
            notice = await asyncio.wait_for(notices.get(), timeout=5.0)
            assert set(notice) >= {"agent", "reason", "detected_at", "instance_id"}
            assert json.dumps(notice)  # JSON-serializable end to end
        finally:
            collector.cancel()
