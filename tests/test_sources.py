"""Tests for ADR-0052: agent sources (kv_source + subject_source)."""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, KVEntry, MeshMessage


class Reading(BaseModel):
    sensor_id: str
    value: float


class DetectionRecord(BaseModel):
    detection_id: str
    state: str


# --- Subject source ---


class TestSubjectSource:
    async def test_handler_with_pydantic_model(self):
        async with AgentMesh.local() as mesh:
            received: list[Reading] = []

            @mesh.agent(
                AgentSpec(name="sensor-watcher", description="watches sensors"),
                sources=[mesh.subject_source("test.sensor.temperature")],
            )
            async def watcher(reading: Reading) -> None:
                received.append(reading)

            await mesh._subscribe_pending()

            # Publish to the subject; the source should fire the handler.
            await mesh.publish("test.sensor.temperature", Reading(sensor_id="s1", value=42.0))
            await mesh._nc.flush()
            await asyncio.sleep(0.1)

            assert len(received) == 1
            assert received[0].sensor_id == "s1"
            assert received[0].value == 42.0

    async def test_handler_with_bytes_param(self):
        async with AgentMesh.local() as mesh:
            received: list[bytes] = []

            @mesh.agent(
                AgentSpec(name="raw-watcher", description="raw bytes"),
                sources=[mesh.subject_source("test.raw")],
            )
            async def watcher(data: bytes) -> None:
                received.append(data)

            await mesh._subscribe_pending()
            await mesh.publish("test.raw", b"\x00\x01\x02")
            await mesh._nc.flush()
            await asyncio.sleep(0.1)

            assert received == [b"\x00\x01\x02"]

    async def test_handler_with_mesh_message(self):
        async with AgentMesh.local() as mesh:
            received: list[MeshMessage] = []

            @mesh.agent(
                AgentSpec(name="msg-watcher", description="sees full envelope"),
                sources=[mesh.subject_source("test.msg")],
            )
            async def watcher(msg: MeshMessage[Reading]) -> None:
                received.append(msg)

            await mesh._subscribe_pending()
            await mesh.publish("test.msg", Reading(sensor_id="s1", value=1.0))
            await mesh._nc.flush()
            await asyncio.sleep(0.1)

            assert len(received) == 1
            m = received[0]
            assert m.subject == "test.msg"
            assert m.payload == Reading(sensor_id="s1", value=1.0)
            # Auto-stamped headers from publish
            assert "X-Mesh-Instance-Id" in m.headers


# --- KV source ---


class TestKVSource:
    async def test_kv_source_fires_on_new_put(self):
        async with AgentMesh.local() as mesh:
            received: list[KVEntry[DetectionRecord]] = []

            @mesh.agent(
                AgentSpec(name="kv-watcher", description="watches KV"),
                sources=[mesh.kv_source("test.detect.*", on_init="skip")],
            )
            async def watcher(entry: KVEntry[DetectionRecord]) -> None:
                received.append(entry)

            await mesh._subscribe_pending()
            await asyncio.sleep(0.1)  # let watch establish

            await mesh.kv.put_model(
                "test.detect.d1",
                DetectionRecord(detection_id="d1", state="pending"),
            )
            await asyncio.sleep(0.2)

            assert len(received) == 1
            assert received[0].key == "test.detect.d1"
            assert received[0].value.detection_id == "d1"
            assert received[0].value.state == "pending"
            assert received[0].operation == "PUT"

    async def test_kv_source_replay_default(self):
        """on_init=replay (default): existing entries fire the handler at startup."""
        async with AgentMesh.local() as mesh:
            # Pre-populate before agent is subscribed
            await mesh.kv.put_model(
                "test.preexisting.x",
                DetectionRecord(detection_id="x", state="pending"),
            )

            received: list[str] = []

            @mesh.agent(
                AgentSpec(name="replay-watcher", description="replays initial"),
                sources=[mesh.kv_source("test.preexisting.*")],  # default on_init=replay
            )
            async def watcher(entry: KVEntry[DetectionRecord]) -> None:
                received.append(entry.key)

            await mesh._subscribe_pending()
            await asyncio.sleep(0.3)

            assert "test.preexisting.x" in received

    async def test_kv_source_skip_does_not_replay(self):
        async with AgentMesh.local() as mesh:
            await mesh.kv.put("test.skip.x", "before")

            received: list[str] = []

            @mesh.agent(
                AgentSpec(name="skip-watcher", description="skips initial"),
                sources=[mesh.kv_source("test.skip.*", on_init="skip")],
            )
            async def watcher(entry: KVEntry[bytes]) -> None:
                received.append(entry.key)

            await mesh._subscribe_pending()
            await asyncio.sleep(0.2)
            # No initial replay, so received should be empty.
            assert received == []

            # New write triggers the handler.
            await mesh.kv.put("test.skip.y", "after")
            await asyncio.sleep(0.2)
            assert "test.skip.y" in received

    async def test_kv_source_handler_with_bytes(self):
        async with AgentMesh.local() as mesh:
            received: list[bytes] = []

            @mesh.agent(
                AgentSpec(name="bytes-watcher", description="bytes-only"),
                sources=[mesh.kv_source("test.bytes.*", on_init="skip")],
            )
            async def watcher(value: bytes) -> None:
                received.append(value)

            await mesh._subscribe_pending()
            await asyncio.sleep(0.1)

            await mesh.kv.put("test.bytes.x", "raw")
            await asyncio.sleep(0.2)

            assert b"raw" in received

    async def test_kv_source_handler_with_model(self):
        async with AgentMesh.local() as mesh:
            received: list[DetectionRecord] = []

            @mesh.agent(
                AgentSpec(name="model-watcher", description="model-only"),
                sources=[mesh.kv_source("test.model.*", on_init="skip")],
            )
            async def watcher(detection: DetectionRecord) -> None:
                received.append(detection)

            await mesh._subscribe_pending()
            await asyncio.sleep(0.1)

            await mesh.kv.put_model(
                "test.model.d1",
                DetectionRecord(detection_id="d1", state="pending"),
            )
            await asyncio.sleep(0.2)

            assert len(received) == 1
            assert received[0].detection_id == "d1"

    async def test_kv_source_model_handler_skips_delete(self):
        """DELETE entries (empty bytes) must not be validated as the model.

        Sparse-KV deletes (e.g. wildfire 'cell off' click) deliver entry.value=b''.
        Model-kind handlers can't construct a model from empty bytes, so the SDK
        skips them rather than raising json_invalid on every drain.
        """
        async with AgentMesh.local() as mesh:
            received: list[DetectionRecord] = []

            @mesh.agent(
                AgentSpec(name="del-model-watcher", description="model + delete"),
                sources=[mesh.kv_source("test.delete.*", on_init="skip")],
            )
            async def watcher(detection: DetectionRecord) -> None:
                received.append(detection)

            await mesh._subscribe_pending()
            await asyncio.sleep(0.1)

            await mesh.kv.put_model(
                "test.delete.d1",
                DetectionRecord(detection_id="d1", state="pending"),
            )
            await asyncio.sleep(0.2)
            assert len(received) == 1

            await mesh.kv.delete("test.delete.d1")
            await asyncio.sleep(0.2)
            # Handler must NOT have been re-invoked (no validation error,
            # no extra entry).
            assert len(received) == 1

    async def test_kv_source_kv_entry_handler_sees_delete(self):
        """KVEntry-kind handlers still receive DELETE ops (raw value passthrough)."""
        async with AgentMesh.local() as mesh:
            received: list[KVEntry[bytes]] = []

            @mesh.agent(
                AgentSpec(name="del-entry-watcher", description="entry + delete"),
                sources=[mesh.kv_source("test.delete2.*", on_init="skip")],
            )
            async def watcher(entry: KVEntry[bytes]) -> None:
                received.append(entry)

            await mesh._subscribe_pending()
            await asyncio.sleep(0.1)

            await mesh.kv.put("test.delete2.x", "v1")
            await asyncio.sleep(0.2)
            await mesh.kv.delete("test.delete2.x")
            await asyncio.sleep(0.2)

            ops = [e.operation for e in received]
            assert "PUT" in ops
            assert "DELETE" in ops

    async def test_kv_source_kv_entry_model_handler_gets_none_on_delete(self):
        """KVEntry[Model] handlers get value=None on DELETE, not a b'' validation.

        Regression: the DEL marker carries empty bytes; validating them as the
        model raised json_invalid on every sparse-KV delete (wildfire cell decay).
        """
        async with AgentMesh.local() as mesh:
            received: list[KVEntry[DetectionRecord]] = []

            @mesh.agent(
                AgentSpec(name="del-model-entry-watcher", description="model entry + delete"),
                sources=[mesh.kv_source("test.delete3.*", on_init="skip")],
            )
            async def watcher(entry: KVEntry[DetectionRecord]) -> None:
                received.append(entry)

            await mesh._subscribe_pending()
            await asyncio.sleep(0.1)

            await mesh.kv.put_model(
                "test.delete3.d1",
                DetectionRecord(detection_id="d1", state="pending"),
            )
            await asyncio.sleep(0.2)
            await mesh.kv.delete("test.delete3.d1")
            await asyncio.sleep(0.2)

            assert [e.operation for e in received] == ["PUT", "DELETE"]
            assert received[0].value is not None
            assert received[0].value.detection_id == "d1"
            assert received[1].value is None


# --- Catalog visibility ---


class TestSourceCatalogVisibility:
    async def test_source_only_agent_in_catalog_as_watcher(self):
        """A no-input handler with sources is classified as Watcher in catalog."""
        async with AgentMesh.local() as mesh:
            received: list[bytes] = []

            @mesh.agent(
                AgentSpec(name="watcher.x", description="source-only"),
                sources=[mesh.subject_source("test.cat.events")],
            )
            async def watcher() -> None:
                received.append(b"fired")

            await mesh._subscribe_pending()
            catalog = await mesh.catalog()

            entry = next((e for e in catalog if e.name == "watcher.x"), None)
            assert entry is not None
            # No input, no return, no yield -> Watcher capability per ADR-0031.
            assert entry.invocable is False
            assert entry.streaming is False

            # Source still drives the handler.
            await mesh.publish("test.cat.events", b"x")
            await mesh._nc.flush()
            await asyncio.sleep(0.1)
            assert received == [b"fired"]
