"""Tests for ObjectStore workspace (mesh-artifacts bucket).

Exercises ADR-0010: Object Store in Phase 1.
Each test uses AgentMesh.local() for a fully isolated embedded NATS instance.
"""

import asyncio

import pytest

from openagentmesh import AgentMesh


# ---------------------------------------------------------------------------
# Layer 2: Technical invariants
# ---------------------------------------------------------------------------


class TestWorkspacePutGet:
    """Basic put/get round-trip through the Object Store."""

    async def test_put_bytes_and_get_returns_same_bytes(self):
        async with AgentMesh.local() as mesh:
            data = b"hello world"
            await mesh.workspace.put("test/greeting.txt", data)

            result = await mesh.workspace.get("test/greeting.txt")
            assert result == data

    async def test_put_str_converts_to_bytes(self):
        async with AgentMesh.local() as mesh:
            await mesh.workspace.put("test/note.txt", "string content")

            result = await mesh.workspace.get("test/note.txt")
            assert result == b"string content"

    async def test_put_overwrites_existing_key(self):
        async with AgentMesh.local() as mesh:
            await mesh.workspace.put("test/file.bin", b"version-1")
            await mesh.workspace.put("test/file.bin", b"version-2")

            result = await mesh.workspace.get("test/file.bin")
            assert result == b"version-2"

    async def test_put_large_binary(self):
        async with AgentMesh.local() as mesh:
            data = b"\x00\xff" * 100_000  # 200 KB
            await mesh.workspace.put("test/large.bin", data)

            result = await mesh.workspace.get("test/large.bin")
            assert result == data


class TestWorkspaceDelete:
    """Delete removes artifacts from the Object Store."""

    async def test_delete_makes_get_fail(self):
        async with AgentMesh.local() as mesh:
            await mesh.workspace.put("test/temp.txt", b"temporary")
            await mesh.workspace.delete("test/temp.txt")

            with pytest.raises(Exception):
                await mesh.workspace.get("test/temp.txt")


class TestWorkspaceIsolation:
    """Different keys are independent."""

    async def test_independent_keys(self):
        async with AgentMesh.local() as mesh:
            await mesh.workspace.put("a/data.bin", b"aaa")
            await mesh.workspace.put("b/data.bin", b"bbb")

            assert await mesh.workspace.get("a/data.bin") == b"aaa"
            assert await mesh.workspace.get("b/data.bin") == b"bbb"

            await mesh.workspace.delete("a/data.bin")
            assert await mesh.workspace.get("b/data.bin") == b"bbb"


# ---------------------------------------------------------------------------
# Layer 1: Business behavior -- agent sharing artifacts
# ---------------------------------------------------------------------------


class TestAgentArtifactSharing:
    """An agent stores an artifact; another agent reads it via the same mesh."""

    async def test_producer_consumer_share_artifact(self):
        from pydantic import BaseModel
        from openagentmesh import AgentSpec

        class StoreRequest(BaseModel):
            key: str
            content: str

        class StoreResult(BaseModel):
            key: str
            size: int

        class FetchRequest(BaseModel):
            key: str

        class FetchResult(BaseModel):
            content: str

        async with AgentMesh.local() as mesh:

            @mesh.agent(AgentSpec(
                name="artifact-writer",
                description="Stores text as a binary artifact in the workspace",
            ))
            async def writer(req: StoreRequest) -> StoreResult:
                data = req.content.encode()
                await mesh.workspace.put(req.key, data)
                return StoreResult(key=req.key, size=len(data))

            @mesh.agent(AgentSpec(
                name="artifact-reader",
                description="Reads a binary artifact from the workspace",
            ))
            async def reader(req: FetchRequest) -> FetchResult:
                data = await mesh.workspace.get(req.key)
                return FetchResult(content=data.decode())

            # Writer stores
            write_result = await mesh.call(
                "artifact-writer",
                {"key": "docs/report.txt", "content": "quarterly earnings report"},
            )
            assert write_result["size"] == len("quarterly earnings report")

            # Reader retrieves
            read_result = await mesh.call(
                "artifact-reader",
                {"key": "docs/report.txt"},
            )
            assert read_result["content"] == "quarterly earnings report"

    async def test_concurrent_writers(self):
        """Multiple agents writing different keys concurrently."""
        async with AgentMesh.local() as mesh:
            async def write_chunk(i: int):
                data = f"chunk-{i}-content".encode()
                await mesh.workspace.put(f"chunks/{i}.txt", data)

            await asyncio.gather(*[write_chunk(i) for i in range(5)])

            for i in range(5):
                result = await mesh.workspace.get(f"chunks/{i}.txt")
                assert result == f"chunk-{i}-content".encode()
