"""Tests for error topic publishing: handler errors are published to mesh.errors.{channel}.{name}."""

import asyncio
import json

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, MeshError


class SimpleInput(BaseModel):
    text: str


class SimpleOutput(BaseModel):
    result: str


class TestErrorTopicPublishing:
    async def test_handler_error_published_to_error_subject(self):
        spec = AgentSpec(name="fail-agent", description="Always fails")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def fail_agent(req: SimpleInput) -> SimpleOutput:
                raise ValueError("something went wrong")

            received = []

            async def on_error(msg):
                received.append(json.loads(msg.data))

            await mesh._nc.subscribe("mesh.errors.fail-agent", cb=on_error)

            with pytest.raises(MeshError, match="something went wrong"):
                await mesh.call("fail-agent", {"text": "hello"})

            await asyncio.sleep(0.1)

            assert len(received) == 1
            assert received[0]["code"] == "handler_error"
            assert "something went wrong" in received[0]["message"]
            assert received[0]["agent"] == "fail-agent"

    async def test_handler_error_with_channel_published_to_error_subject(self):
        spec = AgentSpec(
            name="fail-agent",
            channel="nlp",
            description="Always fails",
        )

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def fail_agent(req: SimpleInput) -> SimpleOutput:
                raise ValueError("channel error")

            received = []

            async def on_error(msg):
                received.append(json.loads(msg.data))

            await mesh._nc.subscribe("mesh.errors.nlp.fail-agent", cb=on_error)

            with pytest.raises(MeshError, match="channel error"):
                await mesh.call("fail-agent", {"text": "hello"})

            await asyncio.sleep(0.1)

            assert len(received) == 1
            assert received[0]["code"] == "handler_error"
            assert "channel error" in received[0]["message"]
            assert received[0]["agent"] == "fail-agent"

    async def test_streaming_error_published_to_error_subject(self):
        spec = AgentSpec(name="fail-agent", description="Fails mid-stream")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def fail_agent(req: SimpleInput) -> SimpleOutput:
                yield SimpleOutput(result="partial")
                raise ValueError("stream exploded")

            received = []

            async def on_error(msg):
                received.append(json.loads(msg.data))

            await mesh._nc.subscribe("mesh.errors.fail-agent", cb=on_error)

            chunks = []
            with pytest.raises(MeshError, match="stream exploded"):
                async for chunk in mesh.stream("fail-agent", {"text": "hello"}):
                    chunks.append(chunk["result"])

            assert chunks == ["partial"]

            await asyncio.sleep(0.1)

            assert len(received) == 1
            assert received[0]["code"] == "handler_error"
            assert "stream exploded" in received[0]["message"]
            assert received[0]["agent"] == "fail-agent"
