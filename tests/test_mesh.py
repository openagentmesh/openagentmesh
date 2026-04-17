"""Integration tests for AgentMesh core: local(), @mesh.agent, call, catalog.

Exercises ADRs 0022, 0024, 0028, 0030, 0031.
Each test uses AgentMesh.local() for a fully isolated embedded NATS instance.
"""

import asyncio

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, CatalogEntry, MeshError


# --- Test models ---


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    reply: str


class SummarizeInput(BaseModel):
    text: str


class SummarizeChunk(BaseModel):
    delta: str


# --- Hello World (ADR-0022, 0030) ---


class TestHelloWorld:
    async def test_register_and_call(self):
        """Simplest end-to-end: one agent, one call."""
        spec = AgentSpec(name="echo", description="Echoes messages")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def echo(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=f"Echo: {req.message}")

            result = await mesh.call("echo", {"message": "hello"})
            assert result["reply"] == "Echo: hello"

    async def test_call_with_pydantic_input(self):
        """mesh.call() accepts Pydantic models as payload."""
        spec = AgentSpec(name="echo", description="Echoes messages")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def echo(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=f"Echo: {req.message}")

            result = await mesh.call("echo", EchoInput(message="world"))
            assert result["reply"] == "Echo: world"


# --- Capability inference (ADR-0031) ---


class TestCapabilityInference:
    async def test_buffered_agent_catalog(self):
        """Buffered handler: invocable=True, streaming=False in catalog."""
        spec = AgentSpec(name="buf", channel="test", description="Buffered")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def buf(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            catalog = await mesh.catalog()

            assert len(catalog) == 1
            assert isinstance(catalog[0], CatalogEntry)
            assert catalog[0].name == "buf"
            assert catalog[0].channel == "test"
            assert catalog[0].invocable is True
            assert catalog[0].streaming is False

    async def test_streaming_agent_catalog(self):
        """Streaming handler: invocable=True, streaming=True in catalog."""
        spec = AgentSpec(name="streamer", description="Streams chunks")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def streamer(req: SummarizeInput) -> SummarizeChunk:
                for word in req.text.split():
                    yield SummarizeChunk(delta=word)

            catalog = await mesh.catalog()

            assert len(catalog) == 1
            assert catalog[0].invocable is True
            assert catalog[0].streaming is True


# --- Catalog filtering (ADR-0028, 0031) ---


class TestCatalog:
    async def test_filter_by_channel(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="a", channel="nlp", description="NLP agent"))
            async def a(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            @mesh.agent(AgentSpec(name="b", channel="finance", description="Finance agent"))
            async def b(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            nlp = await mesh.catalog(channel="nlp")
            assert len(nlp) == 1
            assert nlp[0].name == "a"

    async def test_filter_by_tags(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="a", description="A", tags=["text", "nlp"]))
            async def a(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            @mesh.agent(AgentSpec(name="b", description="B", tags=["finance"]))
            async def b(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            nlp = await mesh.catalog(tags=["nlp"])
            assert len(nlp) == 1
            assert nlp[0].name == "a"


# --- Streaming invocation (ADR-0024) ---


class TestStreaming:
    async def test_stream_basic(self):
        """mesh.stream() yields typed chunks from a streaming agent."""
        spec = AgentSpec(name="summarizer", description="Streams words")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def summarizer(req: SummarizeInput) -> SummarizeChunk:
                for word in req.text.split():
                    yield SummarizeChunk(delta=word)

            chunks = []
            async for chunk in mesh.stream("summarizer", {"text": "one two three"}):
                chunks.append(chunk["delta"])

            assert chunks == ["one", "two", "three"]


# --- KV Store ---


class TestKV:
    async def test_put_get(self):
        async with AgentMesh.local() as mesh:
            await mesh.kv.put("key1", "value1")
            result = await mesh.kv.get("key1")
            assert result == "value1"

    async def test_cas(self):
        async with AgentMesh.local() as mesh:
            await mesh.kv.put("counter", "0")

            async with mesh.kv.cas("counter") as entry:
                val = int(entry.value)
                entry.value = str(val + 1)

            result = await mesh.kv.get("counter")
            assert result == "1"

    async def test_watch(self):
        async with AgentMesh.local() as mesh:
            await mesh.kv.put("key", "v0")

            updates = []

            async def watcher():
                async for value in mesh.kv.watch("key"):
                    updates.append(value)
                    if value == "v2":
                        break

            async def updater():
                await asyncio.sleep(0.05)
                await mesh.kv.put("key", "v1")
                await asyncio.sleep(0.05)
                await mesh.kv.put("key", "v2")

            await asyncio.gather(
                asyncio.wait_for(watcher(), timeout=5.0),
                updater(),
            )

            assert "v1" in updates
            assert "v2" in updates


# --- Error handling ---


class TestErrors:
    async def test_handler_error_propagates(self):
        spec = AgentSpec(name="fail", description="Always fails")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def fail(req: EchoInput) -> EchoOutput:
                raise ValueError("intentional error")

            with pytest.raises(MeshError, match="intentional error"):
                await mesh.call("fail", {"message": "boom"})


# --- Multiple agents ---


class TestMultipleAgents:
    async def test_two_agents_same_mesh(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="upper", description="Uppercase"))
            async def upper(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message.upper())

            @mesh.agent(AgentSpec(name="lower", description="Lowercase"))
            async def lower(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message.lower())

            r1 = await mesh.call("upper", {"message": "Hello"})
            r2 = await mesh.call("lower", {"message": "Hello"})

            assert r1["reply"] == "HELLO"
            assert r2["reply"] == "hello"

    async def test_concurrent_calls(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="slow", description="Slow echo"))
            async def slow(req: EchoInput) -> EchoOutput:
                await asyncio.sleep(0.1)
                return EchoOutput(reply=req.message)

            results = await asyncio.gather(
                mesh.call("slow", {"message": "a"}),
                mesh.call("slow", {"message": "b"}),
                mesh.call("slow", {"message": "c"}),
            )

            replies = sorted(r["reply"] for r in results)
            assert replies == ["a", "b", "c"]
