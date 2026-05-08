"""Tests for ADR-0058: public mesh.publish(subject, payload)."""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh


X_MESH_INSTANCE_ID = "X-Mesh-Instance-Id"
X_MESH_REQUEST_ID = "X-Mesh-Request-Id"
X_MESH_CONTENT_TYPE = "X-Mesh-Content-Type"


class Reading(BaseModel):
    sensor_id: str
    value: float


# --- Payload encoding ---


class TestPublishPayloadTypes:
    async def test_publish_pydantic_model(self):
        async with AgentMesh.local() as mesh:
            received: list[bytes] = []
            received_headers: list[dict[str, str]] = []

            async def cb(msg):
                received.append(msg.data)
                received_headers.append(dict(msg.headers or {}))

            sub = await mesh._nc.subscribe("test.pub.model", cb=cb)
            await mesh._nc.flush()

            payload = Reading(sensor_id="s1", value=42.0)
            await mesh.publish("test.pub.model", payload)

            await mesh._nc.flush()
            await asyncio.sleep(0.05)
            await sub.unsubscribe()

            assert len(received) == 1
            assert json.loads(received[0]) == {"sensor_id": "s1", "value": 42.0}
            assert received_headers[0].get(X_MESH_CONTENT_TYPE) == "application/json"

    async def test_publish_bytes(self):
        async with AgentMesh.local() as mesh:
            received: list[bytes] = []
            received_headers: list[dict[str, str]] = []

            async def cb(msg):
                received.append(msg.data)
                received_headers.append(dict(msg.headers or {}))

            sub = await mesh._nc.subscribe("test.pub.bytes", cb=cb)
            await mesh._nc.flush()

            await mesh.publish("test.pub.bytes", b"\x00\x01\x02raw")

            await mesh._nc.flush()
            await asyncio.sleep(0.05)
            await sub.unsubscribe()

            assert received == [b"\x00\x01\x02raw"]
            assert received_headers[0].get(X_MESH_CONTENT_TYPE) == "application/octet-stream"

    async def test_publish_str(self):
        async with AgentMesh.local() as mesh:
            received: list[bytes] = []
            received_headers: list[dict[str, str]] = []

            async def cb(msg):
                received.append(msg.data)
                received_headers.append(dict(msg.headers or {}))

            sub = await mesh._nc.subscribe("test.pub.text", cb=cb)
            await mesh._nc.flush()

            await mesh.publish("test.pub.text", "hello world")

            await mesh._nc.flush()
            await asyncio.sleep(0.05)
            await sub.unsubscribe()

            assert received == [b"hello world"]
            assert received_headers[0].get(X_MESH_CONTENT_TYPE) == "text/plain"


# --- Auto-stamped headers ---


class TestPublishHeaders:
    async def test_headers_include_instance_id(self):
        async with AgentMesh.local() as mesh:
            received: list[dict[str, str]] = []

            async def cb(msg):
                received.append(dict(msg.headers or {}))

            sub = await mesh._nc.subscribe("test.pub.headers", cb=cb)
            await mesh._nc.flush()

            await mesh.publish("test.pub.headers", "x")
            await mesh._nc.flush()
            await asyncio.sleep(0.05)
            await sub.unsubscribe()

            assert received[0].get(X_MESH_INSTANCE_ID) == mesh.instance_id

    async def test_headers_include_unique_request_id(self):
        async with AgentMesh.local() as mesh:
            received: list[dict[str, str]] = []

            async def cb(msg):
                received.append(dict(msg.headers or {}))

            sub = await mesh._nc.subscribe("test.pub.rid", cb=cb)
            await mesh._nc.flush()

            await mesh.publish("test.pub.rid", "a")
            await mesh.publish("test.pub.rid", "b")
            await mesh._nc.flush()
            await asyncio.sleep(0.05)
            await sub.unsubscribe()

            ids = [h.get(X_MESH_REQUEST_ID) for h in received]
            assert all(i and len(i) == 32 for i in ids)
            assert ids[0] != ids[1]

    async def test_user_headers_take_priority(self):
        async with AgentMesh.local() as mesh:
            received: list[dict[str, str]] = []

            async def cb(msg):
                received.append(dict(msg.headers or {}))

            sub = await mesh._nc.subscribe("test.pub.userhdr", cb=cb)
            await mesh._nc.flush()

            await mesh.publish(
                "test.pub.userhdr",
                "x",
                headers={
                    X_MESH_REQUEST_ID: "user-rid",
                    "X-Custom": "demo",
                },
            )
            await mesh._nc.flush()
            await asyncio.sleep(0.05)
            await sub.unsubscribe()

            assert received[0].get(X_MESH_REQUEST_ID) == "user-rid"
            assert received[0].get("X-Custom") == "demo"
            # instance id default still applies (not overridden by user)
            assert received[0].get(X_MESH_INSTANCE_ID) == mesh.instance_id


# --- Validation ---


class TestPublishValidation:
    async def test_wildcard_subject_rejected_star(self):
        async with AgentMesh.local() as mesh:
            with pytest.raises(ValueError, match="wildcard"):
                await mesh.publish("test.*.event", "x")

    async def test_wildcard_subject_rejected_gt(self):
        async with AgentMesh.local() as mesh:
            with pytest.raises(ValueError, match="wildcard"):
                await mesh.publish("test.events.>", "x")

    async def test_empty_subject_rejected(self):
        async with AgentMesh.local() as mesh:
            with pytest.raises(ValueError):
                await mesh.publish("", "x")

    async def test_publish_without_connection_raises(self):
        mesh = AgentMesh()  # never entered context
        with pytest.raises((AssertionError, RuntimeError)):
            await mesh.publish("test.subject", "x")
