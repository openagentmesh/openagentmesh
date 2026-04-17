"""Tests for mesh.subscribe() with raw subject support (ADR-0034).

Exercises the async generator subscription pattern using direct
NATS publish to simulate event sources.
"""

import asyncio
import json

import pytest

from openagentmesh import AgentMesh, MeshError
from openagentmesh._models import MeshTimeout


# --- Raw subject subscription ---


class TestSubscribeRawSubject:
    async def test_receives_message_on_subject(self):
        """subscribe(subject=) yields a JSON message when stream-end is set."""
        subject = "test.events.single"

        async with AgentMesh.local() as mesh:
            received = []

            async def publisher():
                await asyncio.sleep(0.05)
                await mesh._nc.publish(
                    subject,
                    json.dumps({"event": "hello"}).encode(),
                    headers={
                        "X-Mesh-Stream-End": "true",
                    },
                )

            async def subscriber():
                async for msg in mesh.subscribe(subject=subject):
                    received.append(msg)

            await asyncio.gather(
                asyncio.wait_for(subscriber(), timeout=5.0),
                publisher(),
            )

            assert len(received) == 1
            assert received[0]["event"] == "hello"

    async def test_terminal_flag_closes_generator(self):
        """Two data messages then a bare end-flag: generator yields 2 dicts."""
        subject = "test.events.multi"

        async with AgentMesh.local() as mesh:
            received = []

            async def publisher():
                await asyncio.sleep(0.05)
                for i in range(2):
                    await mesh._nc.publish(
                        subject,
                        json.dumps({"seq": i}).encode(),
                        headers={"X-Mesh-Stream-End": "false"},
                    )
                    await asyncio.sleep(0.01)
                # Terminal: empty body, end=true
                await mesh._nc.publish(
                    subject,
                    b"",
                    headers={"X-Mesh-Stream-End": "true"},
                )

            async def subscriber():
                async for msg in mesh.subscribe(subject=subject):
                    received.append(msg)

            await asyncio.gather(
                asyncio.wait_for(subscriber(), timeout=5.0),
                publisher(),
            )

            assert len(received) == 2
            assert received[0]["seq"] == 0
            assert received[1]["seq"] == 1

    async def test_error_header_raises_mesh_error(self):
        """X-Mesh-Status: error causes MeshError to be raised."""
        subject = "test.events.error"

        async with AgentMesh.local() as mesh:

            async def publisher():
                await asyncio.sleep(0.05)
                error_body = json.dumps({
                    "code": "agent_crashed",
                    "message": "something broke",
                }).encode()
                await mesh._nc.publish(
                    subject,
                    error_body,
                    headers={
                        "X-Mesh-Status": "error",
                        "X-Mesh-Stream-End": "true",
                    },
                )

            async def subscriber():
                async for _ in mesh.subscribe(subject=subject):
                    pass

            with pytest.raises(MeshError, match="something broke"):
                await asyncio.gather(
                    asyncio.wait_for(subscriber(), timeout=5.0),
                    publisher(),
                )

    async def test_timeout_raises_mesh_timeout(self):
        """No messages within timeout raises MeshTimeout."""
        subject = "test.events.silent"

        async with AgentMesh.local() as mesh:
            with pytest.raises(MeshTimeout):
                async for _ in mesh.subscribe(subject=subject, timeout=0.2):
                    pass

    async def test_break_cleans_up_subscription(self):
        """Breaking out of the generator after 2 messages cleans up."""
        subject = "test.events.break"

        async with AgentMesh.local() as mesh:
            received = []

            async def publisher():
                await asyncio.sleep(0.05)
                for i in range(10):
                    await mesh._nc.publish(
                        subject,
                        json.dumps({"n": i}).encode(),
                        headers={"X-Mesh-Stream-End": "false"},
                    )
                    await asyncio.sleep(0.01)

            async def subscriber():
                async for msg in mesh.subscribe(subject=subject, timeout=2.0):
                    received.append(msg)
                    if len(received) == 2:
                        break

            await asyncio.gather(
                asyncio.wait_for(subscriber(), timeout=5.0),
                publisher(),
            )

            assert len(received) == 2


# --- Validation ---


class TestSubscribeValidation:
    async def test_no_args_raises_value_error(self):
        async with AgentMesh.local() as mesh:
            with pytest.raises(ValueError, match="Provide"):
                async for _ in mesh.subscribe():
                    pass

    async def test_agent_and_subject_raises_value_error(self):
        async with AgentMesh.local() as mesh:
            with pytest.raises(ValueError, match="mutually exclusive"):
                async for _ in mesh.subscribe(agent="x", subject="y"):
                    pass
