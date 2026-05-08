"""Tests for ADR-0060: KV ergonomics extensions on mesh.kv."""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh
from openagentmesh._errors import MeshError


class Detection(BaseModel):
    detection_id: str
    state: str
    severity: float = 0.0


# --- list(prefix) ---


class TestKVList:
    async def test_list_returns_entries_under_prefix(self):
        async with AgentMesh.local() as mesh:
            await mesh.kv.put("wildfire.detection.a", "alpha")
            await mesh.kv.put("wildfire.detection.b", "beta")
            await mesh.kv.put("wildfire.fleet.x", "elsewhere")

            entries = await mesh.kv.list("wildfire.detection.*")

            assert len(entries) == 2
            keys = sorted(e.key for e in entries)
            assert keys == ["wildfire.detection.a", "wildfire.detection.b"]
            for e in entries:
                assert isinstance(e.value, bytes)
                assert e.revision >= 0

    async def test_list_empty_prefix_returns_empty(self):
        async with AgentMesh.local() as mesh:
            entries = await mesh.kv.list("nonexistent.*")
            assert entries == []

    async def test_list_supports_gt_wildcard(self):
        async with AgentMesh.local() as mesh:
            await mesh.kv.put("a.b.c", "x")
            await mesh.kv.put("a.b.d.e", "y")

            entries = await mesh.kv.list("a.b.>")
            keys = sorted(e.key for e in entries)
            assert keys == ["a.b.c", "a.b.d.e"]


# --- try_cas ---


class TestKVTryCas:
    async def test_try_cas_succeeds_when_no_concurrent_writer(self):
        async with AgentMesh.local() as mesh:
            await mesh.kv.put("ctr", "0")

            async with mesh.kv.try_cas("ctr") as entry:
                entry.value = "1"

            assert entry.committed is True
            value = await mesh.kv.get("ctr")
            assert value == "1"

    async def test_try_cas_fails_silently_on_conflict(self):
        async with AgentMesh.local() as mesh:
            await mesh.kv.put("ctr", "0")

            async with mesh.kv.try_cas("ctr") as entry:
                # Simulate concurrent writer between read and write
                await mesh.kv.put("ctr", "concurrent")
                entry.value = "1"  # this CAS will fail

            assert entry.committed is False
            value = await mesh.kv.get("ctr")
            assert value == "concurrent"

    async def test_try_cas_no_mutation_committed_true(self):
        """If user does not mutate value, no write attempted; committed True."""
        async with AgentMesh.local() as mesh:
            await mesh.kv.put("ctr", "0")

            async with mesh.kv.try_cas("ctr") as entry:
                _ = entry.value  # read but no mutation

            assert entry.committed is True
            value = await mesh.kv.get("ctr")
            assert value == "0"


# --- create (put-if-absent) ---


class TestKVCreate:
    async def test_create_succeeds_when_absent(self):
        async with AgentMesh.local() as mesh:
            rev = await mesh.kv.create("new.key", "value")
            assert rev > 0
            assert await mesh.kv.get("new.key") == "value"

    async def test_create_raises_when_exists(self):
        from openagentmesh._errors import KVKeyExists

        async with AgentMesh.local() as mesh:
            await mesh.kv.put("existing", "first")
            with pytest.raises(KVKeyExists):
                await mesh.kv.create("existing", "second")

            assert await mesh.kv.get("existing") == "first"

    async def test_create_accepts_pydantic_model(self):
        async with AgentMesh.local() as mesh:
            d = Detection(detection_id="d1", state="pending", severity=0.7)
            rev = await mesh.kv.create("wildfire.detection.d1", d)
            assert rev > 0


# --- Model helpers ---


class TestKVModelHelpers:
    async def test_put_get_model_round_trip(self):
        async with AgentMesh.local() as mesh:
            d = Detection(detection_id="d1", state="pending", severity=0.5)
            await mesh.kv.put_model("wildfire.detection.d1", d)

            loaded = await mesh.kv.get_model("wildfire.detection.d1", Detection)
            assert loaded == d

    async def test_list_models_returns_validated_entries(self):
        async with AgentMesh.local() as mesh:
            d1 = Detection(detection_id="d1", state="pending")
            d2 = Detection(detection_id="d2", state="surveyed", severity=0.9)
            await mesh.kv.put_model("wildfire.detection.d1", d1)
            await mesh.kv.put_model("wildfire.detection.d2", d2)

            entries = await mesh.kv.list_models("wildfire.detection.*", Detection)
            assert len(entries) == 2
            ids = sorted(e.value.detection_id for e in entries)
            assert ids == ["d1", "d2"]
            for e in entries:
                assert isinstance(e.value, Detection)

    async def test_cas_model_round_trip(self):
        async with AgentMesh.local() as mesh:
            d = Detection(detection_id="d1", state="pending")
            await mesh.kv.put_model("wildfire.detection.d1", d)

            async with mesh.kv.cas_model("wildfire.detection.d1", Detection) as entry:
                entry.value.state = "assigned:drone-3"

            loaded = await mesh.kv.get_model("wildfire.detection.d1", Detection)
            assert loaded.state == "assigned:drone-3"

    async def test_try_cas_model_election_pattern(self):
        async with AgentMesh.local() as mesh:
            d = Detection(detection_id="d1", state="pending")
            await mesh.kv.put_model("wildfire.detection.d1", d)

            # Simulate two-drone race: drone A wins, drone B sees pending->assigned.
            async with mesh.kv.try_cas_model(
                "wildfire.detection.d1", Detection
            ) as entry_a:
                if entry_a.value.state == "pending":
                    entry_a.value.state = "assigned:drone-A"

            assert entry_a.committed is True

            async with mesh.kv.try_cas_model(
                "wildfire.detection.d1", Detection
            ) as entry_b:
                if entry_b.value.state == "pending":
                    entry_b.value.state = "assigned:drone-B"

            # Drone B saw "assigned:drone-A", chose not to mutate; committed True (vacuous).
            assert entry_b.committed is True
            loaded = await mesh.kv.get_model("wildfire.detection.d1", Detection)
            assert loaded.state == "assigned:drone-A"


# --- KVEntry public class ---


class TestKVEntryPublic:
    async def test_entry_has_required_fields(self):
        async with AgentMesh.local() as mesh:
            await mesh.kv.put("entry.test", "v")

            entries = await mesh.kv.list("entry.*")
            assert len(entries) == 1
            e = entries[0]
            assert e.key == "entry.test"
            assert e.value == b"v"
            assert isinstance(e.revision, int)
            assert e.operation in ("PUT", "DELETE")
