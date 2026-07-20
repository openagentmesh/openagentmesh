"""Tests for ADR-0023: LLM cost model and usage attribution.

Handlers opt in via ``report_usage(Usage(...))``; the host stamps the
``X-Mesh-Usage`` reply header (stream-end frame for streamers) and publishes
a ``usage_reported`` observe event on ``mesh.logs.{name}``.
"""

import asyncio
import json

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, Usage, report_usage

pytestmark = pytest.mark.asyncio

X_MESH_USAGE = "X-Mesh-Usage"


class In(BaseModel):
    text: str


class Out(BaseModel):
    summary: str


class Chunk(BaseModel):
    delta: str


async def _tap(mesh: AgentMesh, subject: str) -> list[dict]:
    """Collect parsed JSON payloads published on a subject."""
    received: list[dict] = []

    async def on_msg(msg):
        received.append(json.loads(msg.data))

    await mesh._conn.subscribe(subject, cb=on_msg)
    await mesh._conn.flush()
    return received


class TestUsageModel:
    async def test_usage_fields_all_optional(self):
        usage = Usage()
        assert usage.input_tokens is None
        usage = Usage(
            input_tokens=1500,
            output_tokens=300,
            total_tokens=1800,
            model="claude-sonnet-4-20250514",
            estimated_cost_usd=0.0123,
        )
        assert usage.output_tokens == 300

    async def test_report_usage_outside_request_context_raises(self):
        with pytest.raises(RuntimeError):
            report_usage(Usage(input_tokens=1))


class TestResponderUsage:
    async def test_reply_carries_usage_header(self):
        async with AgentMesh.local() as host:
            @host.agent(AgentSpec(name="summarizer", description="summarizes"))
            async def summarizer(req: In) -> Out:
                report_usage(Usage(
                    input_tokens=1500, output_tokens=300, model="test-model"
                ))
                return Out(summary=req.text[:3])

            await host._subscribe_pending()

            async with AgentMesh(host.url) as caller:
                response = await caller._conn.request(
                    "mesh.agent.summarizer",
                    json.dumps({"text": "hello"}).encode(),
                    timeout=2.0,
                    headers={"X-Mesh-Request-Id": "rid-usage-1"},
                )
                raw = (response.headers or {}).get(X_MESH_USAGE)
                assert raw, "reply is missing the X-Mesh-Usage header"
                usage = json.loads(raw)
                assert usage == {
                    "input_tokens": 1500,
                    "output_tokens": 300,
                    "model": "test-model",
                }

    async def test_multiple_reports_accumulate(self):
        """Token/cost fields sum across reports; model keeps the last value."""
        async with AgentMesh.local() as host:
            @host.agent(AgentSpec(name="multi", description="two llm calls"))
            async def multi(req: In) -> Out:
                report_usage(Usage(
                    input_tokens=100, output_tokens=10,
                    estimated_cost_usd=0.001, model="model-a",
                ))
                report_usage(Usage(
                    input_tokens=200, output_tokens=20,
                    estimated_cost_usd=0.002, model="model-b",
                ))
                return Out(summary="done")

            await host._subscribe_pending()

            async with AgentMesh(host.url) as caller:
                response = await caller._conn.request(
                    "mesh.agent.multi",
                    json.dumps({"text": "hi"}).encode(),
                    timeout=2.0,
                    headers={"X-Mesh-Request-Id": "rid-usage-2"},
                )
                usage = json.loads((response.headers or {})[X_MESH_USAGE])
                assert usage["input_tokens"] == 300
                assert usage["output_tokens"] == 30
                assert usage["estimated_cost_usd"] == pytest.approx(0.003)
                assert usage["model"] == "model-b"

    async def test_non_reporting_agent_has_no_header(self):
        async with AgentMesh.local() as host:
            @host.agent(AgentSpec(name="plain", description="deterministic"))
            async def plain(req: In) -> Out:
                return Out(summary=req.text)

            await host._subscribe_pending()

            async with AgentMesh(host.url) as caller:
                response = await caller._conn.request(
                    "mesh.agent.plain",
                    json.dumps({"text": "hi"}).encode(),
                    timeout=2.0,
                    headers={"X-Mesh-Request-Id": "rid-usage-3"},
                )
                assert X_MESH_USAGE not in (response.headers or {})

    async def test_usage_isolated_between_requests(self):
        """A second request does not inherit the first request's usage."""
        async with AgentMesh.local() as host:
            calls = [0]

            @host.agent(AgentSpec(name="once", description="reports once"))
            async def once(req: In) -> Out:
                calls[0] += 1
                if calls[0] == 1:
                    report_usage(Usage(input_tokens=42))
                return Out(summary="ok")

            await host._subscribe_pending()

            async with AgentMesh(host.url) as caller:
                first = await caller._conn.request(
                    "mesh.agent.once", json.dumps({"text": "a"}).encode(),
                    timeout=2.0, headers={"X-Mesh-Request-Id": "rid-a"},
                )
                second = await caller._conn.request(
                    "mesh.agent.once", json.dumps({"text": "b"}).encode(),
                    timeout=2.0, headers={"X-Mesh-Request-Id": "rid-b"},
                )
                assert X_MESH_USAGE in (first.headers or {})
                assert X_MESH_USAGE not in (second.headers or {})


class TestStreamerUsage:
    async def test_end_frame_carries_usage_header(self):
        async with AgentMesh.local() as host:
            @host.agent(AgentSpec(name="streamer", description="streams"))
            async def streamer(req: In) -> Chunk:
                for word in req.text.split():
                    yield Chunk(delta=word)
                report_usage(Usage(input_tokens=50, output_tokens=5))

            await host._subscribe_pending()

            async with AgentMesh(host.url) as caller:
                frames: list[tuple[dict, bytes]] = []
                done = asyncio.Event()

                async def on_frame(msg):
                    frames.append((dict(msg.headers or {}), msg.data))
                    if (msg.headers or {}).get("X-Mesh-Stream-End") == "true":
                        done.set()

                rid = "rid-stream-usage"
                sub = await caller._conn.subscribe(f"mesh.stream.{rid}", cb=on_frame)
                await caller._conn.flush()
                await caller._conn.publish(
                    "mesh.agent.streamer",
                    json.dumps({"text": "one two"}).encode(),
                    headers={"X-Mesh-Request-Id": rid, "X-Mesh-Stream": "true"},
                )
                await caller._conn.flush()
                await asyncio.wait_for(done.wait(), timeout=5.0)
                await sub.unsubscribe()

                end_headers = frames[-1][0]
                assert end_headers.get("X-Mesh-Stream-End") == "true"
                usage = json.loads(end_headers[X_MESH_USAGE])
                assert usage == {"input_tokens": 50, "output_tokens": 5}
                # Chunk frames carry no usage header.
                for headers, _ in frames[:-1]:
                    assert X_MESH_USAGE not in headers


class TestUsageObserveEvent:
    async def test_usage_reported_event_published(self):
        """Reporting publishes a usage_reported observe event at info level."""
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="tracked", description="tracked"))
            async def tracked(req: In) -> Out:
                report_usage(Usage(input_tokens=7, output_tokens=3, model="m"))
                return Out(summary="ok")

            received = await _tap(mesh, "mesh.logs.tracked")
            result = await mesh.call("tracked", {"text": "hi"})
            assert result == {"summary": "ok"}
            await asyncio.sleep(0.1)

            events = [e for e in received if e["event"] == "usage_reported"]
            assert len(events) == 1
            event = events[0]
            assert event["level"] == "info"
            assert event["agent"] == "tracked"
            assert event["request_id"]
            assert event["data"] == {
                "input_tokens": 7, "output_tokens": 3, "model": "m"
            }

    async def test_no_event_without_report(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="silent", description="silent"))
            async def silent(req: In) -> Out:
                return Out(summary="ok")

            received = await _tap(mesh, "mesh.logs.silent")
            await mesh.call("silent", {"text": "hi"})
            await asyncio.sleep(0.1)

            assert not [e for e in received if e["event"] == "usage_reported"]
