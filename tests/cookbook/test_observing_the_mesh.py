"""Executable twin of docs/cookbook/observing-the-mesh.md.

Same code as the recipe, wrapped in pytest with AgentMesh.local().
"""

import asyncio

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, MeshError

pytestmark = pytest.mark.asyncio


class SummarizeInput(BaseModel):
    text: str


class SummarizeOutput(BaseModel):
    summary: str


async def test_failure_monitor_sees_warn_events():
    """Recipe: 'Watch failures as they happen'."""
    async with AgentMesh.local() as mesh:
        @mesh.agent(AgentSpec(name="nlp.summarizer", description="Summarizes text"))
        async def summarize(req: SummarizeInput) -> SummarizeOutput:
            raise RuntimeError("model overloaded")

        alerts = []

        async def failure_monitor():
            async for event in mesh.observe.logs(level="warn"):
                alerts.append(f"{event.agent}: {event.event} — {event.message}")
                if event.data.get("code") == "handler_error":
                    break

        task = asyncio.create_task(failure_monitor())
        await asyncio.sleep(0.3)  # let the monitor subscribe

        with pytest.raises(MeshError, match="model overloaded"):
            await mesh.call("nlp.summarizer", {"text": "hello"})

        await asyncio.wait_for(task, timeout=5.0)
        assert alerts and "request_failed" in alerts[0]


async def test_debug_session_with_runtime_level_change():
    """Recipe: 'Turn one agent up to debug' + 'Check what's in effect'."""
    async with AgentMesh.local() as mesh:
        @mesh.agent(AgentSpec(name="nlp.summarizer", description="Summarizes text"))
        async def summarize(req: SummarizeInput) -> SummarizeOutput:
            return SummarizeOutput(summary=req.text[:20])

        await mesh.observe.set("nlp.summarizer", log_level="debug")

        durations = []

        async def watch_durations():
            async for event in mesh.observe.logs("nlp.summarizer"):
                if event.event == "request_completed":
                    durations.append(event.data["duration_ms"])
                    break

        task = asyncio.create_task(watch_durations())
        await asyncio.sleep(0.3)

        # Config propagates via KV watch; keep invoking until it lands.
        deadline = asyncio.get_event_loop().time() + 5.0
        while asyncio.get_event_loop().time() < deadline and not task.done():
            await mesh.call("nlp.summarizer", {"text": "hello world"})
            await asyncio.sleep(0.1)
        await asyncio.wait_for(task, timeout=5.0)
        assert durations and durations[0] >= 0

        # Which tier answered?
        config = await mesh.observe.get("nlp.summarizer")
        assert (config.log_level, config.source) == ("debug", "agent")

        config = await mesh.observe.get("nlp.classifier")
        assert (config.log_level, config.source) == ("info", "default")

        # Put it back.
        await mesh.observe.set("nlp.summarizer", log_level="info")
        config = await mesh.observe.get("nlp.summarizer")
        assert config.log_level == "info"
