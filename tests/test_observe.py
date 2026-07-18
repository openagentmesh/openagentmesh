"""Tests for ADR-0048 v1: mesh-native observability.

Structured, level-gated log events on ``mesh.logs.{name}``, controlled by
the ``mesh-observability`` KV bucket, consumed via ``mesh.observe``.
"""

import asyncio
import json

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec
from openagentmesh._errors import InvalidInput, MeshError

pytestmark = pytest.mark.asyncio


class In(BaseModel):
    text: str


class Out(BaseModel):
    summary: str


async def _raw_tap(mesh: AgentMesh, subject: str) -> list[dict]:
    """Subscribe to a raw log subject, collecting parsed payloads."""
    received: list[dict] = []

    async def on_msg(msg):
        received.append(json.loads(msg.data))

    await mesh._conn.subscribe(subject, cb=on_msg)
    await mesh._conn.flush()
    return received


async def _wait_for(received: list, count: int, timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if len(received) >= count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"expected {count} events, got {len(received)}: {received}")


class TestLogPublishing:
    async def test_debug_level_publishes_request_events(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="nlp.summarizer", description="Summarizes"))
            async def summarize(req: In) -> Out:
                return Out(summary=req.text[:10])

            await mesh.observe.set("nlp.summarizer", log_level="debug")
            received = await _raw_tap(mesh, "mesh.logs.nlp.summarizer")

            # Config propagates via KV watch; poll until the host picks it up.
            deadline = asyncio.get_event_loop().time() + 5.0
            while asyncio.get_event_loop().time() < deadline and not received:
                await mesh.call("nlp.summarizer", {"text": "hello world"})
                await asyncio.sleep(0.1)

            await _wait_for(received, 2)
            events = {e["event"] for e in received}
            assert "request_received" in events
            assert "request_completed" in events
            completed = next(e for e in received if e["event"] == "request_completed")
            assert completed["level"] == "debug"
            assert completed["agent"] == "nlp.summarizer"
            assert completed["request_id"]
            assert completed["data"]["duration_ms"] >= 0

    async def test_default_level_suppresses_request_events(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="quiet.agent", description="Default level"))
            async def handler(req: In) -> Out:
                return Out(summary=req.text)

            received = await _raw_tap(mesh, "mesh.logs.quiet.agent")
            await mesh.call("quiet.agent", {"text": "hello"})
            await asyncio.sleep(0.3)
            # request_received/request_completed are debug; default level is info.
            assert received == []

    async def test_request_failed_visible_at_default_level(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="fail.agent", description="Always fails"))
            async def handler(req: In) -> Out:
                raise ValueError("boom")

            received = await _raw_tap(mesh, "mesh.logs.fail.agent")
            with pytest.raises(MeshError, match="boom"):
                await mesh.call("fail.agent", {"text": "hello"})

            await _wait_for(received, 1)
            assert received[0]["event"] == "request_failed"
            assert received[0]["level"] == "warn"

    async def test_validation_error_visible_at_default_level(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="strict.agent", description="Validates"))
            async def handler(req: In) -> Out:
                return Out(summary=req.text)

            received = await _raw_tap(mesh, "mesh.logs.strict.agent")
            with pytest.raises(InvalidInput):
                await mesh.call("strict.agent", {"wrong_field": 42})

            await _wait_for(received, 1)
            assert received[0]["event"] == "validation_error"
            assert received[0]["level"] == "warn"

    async def test_lifecycle_events_published_at_info(self):
        async with AgentMesh.local() as mesh:
            received = await _raw_tap(mesh, "mesh.logs.>")

            host = AgentMesh(mesh.url)

            @host.agent(AgentSpec(name="cycle.agent", description="Lifecycle"))
            async def handler(req: In) -> Out:
                return Out(summary=req.text)

            async with host:
                await _wait_for(received, 1)
                assert received[0]["event"] == "agent_registered"
                assert received[0]["level"] == "info"
                assert received[0]["agent"] == "cycle.agent"

            await _wait_for(received, 2)
            events = [e["event"] for e in received]
            assert "agent_deregistered" in events


class TestObserveConsumer:
    async def test_observe_logs_yields_typed_events(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="nlp.summarizer", description="Summarizes"))
            async def summarize(req: In) -> Out:
                return Out(summary=req.text[:10])

            await mesh.observe.set("nlp.summarizer", log_level="debug")

            collected = []

            async def consume():
                async with AgentMesh(mesh.url) as tap:
                    async for event in tap.observe.logs("nlp.summarizer"):
                        collected.append(event)
                        if len(collected) >= 2:
                            break

            task = asyncio.create_task(consume())
            await asyncio.sleep(0.5)
            deadline = asyncio.get_event_loop().time() + 5.0
            while asyncio.get_event_loop().time() < deadline and not task.done():
                await mesh.call("nlp.summarizer", {"text": "hello"})
                await asyncio.sleep(0.1)
            await asyncio.wait_for(task, timeout=5.0)

            assert len(collected) >= 2
            event = collected[0]
            # Typed LogEvent model, not a raw dict.
            assert event.agent == "nlp.summarizer"
            assert event.level in ("debug", "info", "warn", "error")
            assert event.event
            assert isinstance(event.data, dict)

    async def test_observe_logs_level_filter(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="filter.agent", description="Fails"))
            async def handler(req: In) -> Out:
                raise ValueError("boom")

            await mesh.observe.set("filter.agent", log_level="debug")

            collected = []

            async def consume():
                async with AgentMesh(mesh.url) as tap:
                    # Only warn and above; debug request events filtered out.
                    async for event in tap.observe.logs("filter.agent", level="warn"):
                        collected.append(event)
                        break

            task = asyncio.create_task(consume())
            await asyncio.sleep(0.5)
            deadline = asyncio.get_event_loop().time() + 5.0
            while asyncio.get_event_loop().time() < deadline and not task.done():
                with pytest.raises(MeshError):
                    await mesh.call("filter.agent", {"text": "x"})
                await asyncio.sleep(0.1)
            await asyncio.wait_for(task, timeout=5.0)

            assert collected[0].event == "request_failed"
            assert collected[0].level == "warn"


class TestObserveConfig:
    async def test_default_config(self):
        async with AgentMesh.local() as mesh:
            config = await mesh.observe.get("never.configured")
            assert config.log_level == "info"
            assert config.source == "default"

    async def test_global_config(self):
        async with AgentMesh.local() as mesh:
            await mesh.observe.set_global(log_level="warn")
            config = await mesh.observe.get("never.configured")
            assert config.log_level == "warn"
            assert config.source == "global"

    async def test_per_agent_overrides_global(self):
        async with AgentMesh.local() as mesh:
            await mesh.observe.set_global(log_level="warn")
            await mesh.observe.set("nlp.summarizer", log_level="debug")
            config = await mesh.observe.get("nlp.summarizer")
            assert config.log_level == "debug"
            assert config.source == "agent"
            other = await mesh.observe.get("nlp.other")
            assert other.log_level == "warn"
            assert other.source == "global"

    async def test_runtime_change_applies_without_restart(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="hot.agent", description="Hot reconfig"))
            async def handler(req: In) -> Out:
                return Out(summary=req.text)

            received = await _raw_tap(mesh, "mesh.logs.hot.agent")

            # Default level: silent.
            await mesh.call("hot.agent", {"text": "one"})
            await asyncio.sleep(0.3)
            assert received == []

            # Flip to debug at runtime; the host picks it up via KV watch.
            await mesh.observe.set("hot.agent", log_level="debug")
            deadline = asyncio.get_event_loop().time() + 5.0
            while asyncio.get_event_loop().time() < deadline and not received:
                await mesh.call("hot.agent", {"text": "two"})
                await asyncio.sleep(0.1)
            assert received, "runtime level change never took effect"

    async def test_off_silences_warn_events(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="off.agent", description="Silenced"))
            async def handler(req: In) -> Out:
                raise ValueError("boom")

            await mesh.observe.set("off.agent", log_level="off")
            received = await _raw_tap(mesh, "mesh.logs.off.agent")

            # Config may lag; give the watch a moment before asserting silence.
            await asyncio.sleep(0.5)
            with pytest.raises(MeshError):
                await mesh.call("off.agent", {"text": "x"})
            await asyncio.sleep(0.3)
            assert received == []
