"""Integration tests for AgentMesh core: local(), @mesh.agent, call, catalog.

Exercises ADRs 0022, 0024, 0028, 0030, 0031.
Each test uses AgentMesh.local() for a fully isolated embedded NATS instance.
"""

import asyncio

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, CatalogEntry, MeshError
from openagentmesh._models import InvocationMismatch


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

    async def test_instance_local(self):
        """Instance-level local() reuses handlers registered before entering."""
        mesh = AgentMesh()
        spec = AgentSpec(name="echo", description="Echoes messages")

        @mesh.agent(spec)
        async def echo(req: EchoInput) -> EchoOutput:
            return EchoOutput(reply=f"Echo: {req.message}")

        async with mesh.local():
            result = await mesh.call("echo", {"message": "instance"})
            assert result["reply"] == "Echo: instance"


# --- Capability inference (ADR-0031) ---


class TestCapabilityInference:
    async def test_responder_agent_catalog(self):
        """Responder handler: invocable=True, streaming=False in catalog."""
        spec = AgentSpec(name="test.buf", description="Responder")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def buf(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            catalog = await mesh.catalog()

            assert len(catalog) == 1
            assert isinstance(catalog[0], CatalogEntry)
            assert catalog[0].name == "test.buf"
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
        """ADR-0049: channel filter is a prefix match on dotted name."""
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="nlp.a", description="NLP agent"))
            async def a(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            @mesh.agent(AgentSpec(name="finance.b", description="Finance agent"))
            async def b(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            nlp = await mesh.catalog(channel="nlp")
            assert len(nlp) == 1
            assert nlp[0].name == "nlp.a"

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


# --- Invocation mismatch (ADR-0047) ---


class TestInvocationMismatch:
    async def test_call_publisher_raises(self):
        """mesh.call() against a publisher raises InvocationMismatch."""
        spec = AgentSpec(name="price-feed", description="Emits prices")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def price_feed() -> EchoOutput:
                while True:
                    yield EchoOutput(reply="tick")
                    await asyncio.sleep(1)

            with pytest.raises(InvocationMismatch, match="publisher.*cannot be called"):
                await mesh.call("price-feed")

    async def test_stream_publisher_raises(self):
        """mesh.stream() against a publisher raises InvocationMismatch."""
        spec = AgentSpec(name="events", description="Emits events")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def events() -> EchoOutput:
                while True:
                    yield EchoOutput(reply="event")
                    await asyncio.sleep(1)

            with pytest.raises(InvocationMismatch, match="publisher.*cannot be streamed"):
                async for _ in mesh.stream("events"):
                    pass

    async def test_send_publisher_raises(self):
        """mesh.send() against a publisher raises InvocationMismatch."""
        spec = AgentSpec(name="emitter", description="Emits stuff")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def emitter() -> EchoOutput:
                while True:
                    yield EchoOutput(reply="emit")
                    await asyncio.sleep(1)

            with pytest.raises(InvocationMismatch, match="publisher.*cannot be sent to"):
                await mesh.send("emitter", {"data": "test"})

    async def test_call_watcher_raises(self):
        """mesh.call() against a watcher raises InvocationMismatch."""
        spec = AgentSpec(name="watcher", description="Watches things")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def watcher():
                await asyncio.sleep(3600)

            with pytest.raises(InvocationMismatch, match="background task"):
                await mesh.call("watcher")

    async def test_call_streamer_raises(self):
        """mesh.call() against a streaming agent raises InvocationMismatch."""
        spec = AgentSpec(name="streamer", description="Streaming agent")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def streamer(req: SummarizeInput) -> SummarizeChunk:
                for word in req.text.split():
                    yield SummarizeChunk(delta=word)

            with pytest.raises(InvocationMismatch, match="streaming-only.*stream\\(\\)"):
                await mesh.call("streamer", {"text": "hello world"})

    async def test_stream_responder_raises(self):
        """mesh.stream() against a responder raises InvocationMismatch."""
        spec = AgentSpec(name="responder", description="Responder agent")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def responder(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            with pytest.raises(InvocationMismatch, match="does not support streaming.*call\\(\\)"):
                async for _ in mesh.stream("responder", {"message": "hi"}):
                    pass

    async def test_publisher_hint_suggests_subscribe(self):
        """Publisher mismatch message suggests subscribing."""
        spec = AgentSpec(name="pub", description="Publisher")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def pub() -> EchoOutput:
                while True:
                    yield EchoOutput(reply="x")
                    await asyncio.sleep(1)

            with pytest.raises(InvocationMismatch, match="[Ss]ubscribe"):
                await mesh.call("pub")

    async def test_subscribe_responder_raises(self):
        """mesh.subscribe() against a responder raises InvocationMismatch."""
        spec = AgentSpec(name="resp", description="Responder")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def resp(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            with pytest.raises(InvocationMismatch, match="does not publish.*call\\(\\)"):
                async for _ in mesh.subscribe(agent="resp"):
                    pass

    async def test_subscribe_streamer_raises(self):
        """mesh.subscribe() against a streamer raises InvocationMismatch."""
        spec = AgentSpec(name="str-agent", description="Streamer")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def str_agent(req: SummarizeInput) -> SummarizeChunk:
                yield SummarizeChunk(delta="x")

            with pytest.raises(InvocationMismatch, match="streams responses.*stream\\(\\)"):
                async for _ in mesh.subscribe(agent="str-agent"):
                    pass

    async def test_subscribe_watcher_raises(self):
        """mesh.subscribe() against a watcher raises InvocationMismatch."""
        spec = AgentSpec(name="bg", description="Background")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def bg():
                await asyncio.sleep(3600)

            with pytest.raises(InvocationMismatch, match="background task.*does not publish"):
                async for _ in mesh.subscribe(agent="bg"):
                    pass


# --- Streaming error propagation (ADR-0005) ---


class TestStreamingErrors:
    async def test_handler_error_during_streaming(self):
        """Generator error mid-stream propagates to client as MeshError."""
        spec = AgentSpec(name="failing-stream", description="Fails mid-stream")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def failing_stream(req: SummarizeInput) -> SummarizeChunk:
                yield SummarizeChunk(delta="first")
                raise ValueError("mid-stream failure")

            chunks = []
            with pytest.raises(MeshError, match="mid-stream failure"):
                async for chunk in mesh.stream("failing-stream", {"text": "hello"}):
                    chunks.append(chunk["delta"])

            assert chunks == ["first"]


# --- Catalog change subscription (ADR-0032) ---


class TestCatalogSubscription:
    async def test_cache_populated_on_connect(self):
        """Local agents appear in _catalog_cache immediately after subscription."""
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="echo", description="Echo"))
            async def echo(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            # _subscribe_pending seeds cache synchronously for local agents
            await mesh._subscribe_pending()

            assert "echo" in mesh._catalog_cache
            assert mesh._catalog_cache["echo"].streaming is False

    async def test_remote_agent_appears_in_cache(self):
        """Agent registered on mesh1 appears in mesh2's catalog cache."""
        from openagentmesh._local import EmbeddedNats

        embedded = EmbeddedNats()
        await embedded.start()
        try:
            mesh1 = AgentMesh(url=embedded.url)
            mesh2 = AgentMesh(url=embedded.url)

            async with mesh1, mesh2:
                @mesh1.agent(AgentSpec(name="remote-echo", description="Remote echo"))
                async def remote_echo(req: EchoInput) -> EchoOutput:
                    return EchoOutput(reply=req.message)

                await mesh1._subscribe_pending()

                # Wait for mesh2's watcher to pick up the catalog change
                for _ in range(50):
                    if "remote-echo" in mesh2._catalog_cache:
                        break
                    await asyncio.sleep(0.05)

                assert "remote-echo" in mesh2._catalog_cache
                assert mesh2._catalog_cache["remote-echo"].streaming is False
        finally:
            await embedded.stop()

    async def test_catalog_reads_from_cache(self):
        """mesh.catalog() returns entries from the cache."""
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="nlp.a", description="A"))
            async def a(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            # catalog() calls _subscribe_pending() which seeds cache
            entries = await mesh.catalog()
            assert len(entries) == 1
            assert entries[0].name == "nlp.a"

    async def test_capability_check_uses_cache_for_remote(self):
        """Pre-flight check works for agents only known via catalog cache."""
        from openagentmesh._local import EmbeddedNats

        embedded = EmbeddedNats()
        await embedded.start()
        try:
            mesh1 = AgentMesh(url=embedded.url)
            mesh2 = AgentMesh(url=embedded.url)

            async with mesh1, mesh2:
                @mesh1.agent(AgentSpec(name="remote-buf", description="Responder"))
                async def remote_buf(req: EchoInput) -> EchoOutput:
                    return EchoOutput(reply=req.message)

                await mesh1._subscribe_pending()

                # Wait for cache
                for _ in range(50):
                    if "remote-buf" in mesh2._catalog_cache:
                        break
                    await asyncio.sleep(0.05)

                # mesh2 knows remote-buf is a responder via cache
                with pytest.raises(InvocationMismatch, match="does not support streaming"):
                    async for _ in mesh2.stream("remote-buf", {"message": "hi"}):
                        pass
        finally:
            await embedded.stop()

    async def test_seed_cache_catches_remote_publisher(self):
        """Caller connecting after a publisher registered gets InvocationMismatch, not NoRespondersError."""
        from openagentmesh._local import EmbeddedNats

        embedded = EmbeddedNats()
        await embedded.start()
        try:
            mesh1 = AgentMesh(url=embedded.url)
            async with mesh1:
                @mesh1.agent(AgentSpec(name="remote-pub", description="Publisher"))
                async def remote_pub() -> EchoOutput:
                    while True:
                        yield EchoOutput(reply="tick")
                        await asyncio.sleep(1)

                await mesh1._subscribe_pending()

                # mesh2 connects after publisher is already in the catalog
                mesh2 = AgentMesh(url=embedded.url)
                async with mesh2:
                    assert "remote-pub" in mesh2._catalog_cache
                    with pytest.raises(InvocationMismatch, match="publisher"):
                        await mesh2.call("remote-pub")
        finally:
            await embedded.stop()


# --- Scalar and generic type support (ADR-0046) ---


class TestScalarTypes:
    async def test_scalar_responder(self):
        """str -> str handler works end-to-end."""
        spec = AgentSpec(name="greet", description="Greets by name")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def greet(name: str) -> str:
                return f"Hello, {name}"

            result = await mesh.call("greet", "world")
            assert result == "Hello, world"

    async def test_int_responder(self):
        """int -> int handler works end-to-end."""
        spec = AgentSpec(name="double", description="Doubles a number")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def double(n: int) -> int:
                return n * 2

            result = await mesh.call("double", 21)
            assert result == 42

    async def test_scalar_trigger(self):
        """No-input handler returning int is invocable (trigger)."""
        spec = AgentSpec(name="answer", description="Returns the answer")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def answer() -> int:
                return 42

            result = await mesh.call("answer")
            assert result == 42

    async def test_list_output(self):
        """Handler returning list[str] serializes correctly."""
        spec = AgentSpec(name="split", description="Splits text")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def split(text: str) -> list[str]:
                return text.split()

            result = await mesh.call("split", "one two three")
            assert result == ["one", "two", "three"]

    async def test_scalar_streaming(self):
        """Streaming handler yielding str chunks works."""
        spec = AgentSpec(name="words", description="Yields words")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def words(text: str) -> str:
                for word in text.split():
                    yield word

            chunks = []
            async for chunk in mesh.stream("words", "one two three"):
                chunks.append(chunk)

            assert chunks == ["one", "two", "three"]

    async def test_scalar_contract_schema(self):
        """Scalar types produce correct JSON Schema in the contract."""
        spec = AgentSpec(name="greet", description="Greets by name")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def greet(name: str) -> str:
                return f"Hello, {name}"

            contract = await mesh.contract("greet")
            assert contract.input_schema == {"type": "string"}
            assert contract.output_schema == {"type": "string"}

    async def test_mixed_scalar_input_model_output(self):
        """Scalar input with BaseModel output works."""
        spec = AgentSpec(name="lookup", description="Looks up a name")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def lookup(name: str) -> EchoOutput:
                return EchoOutput(reply=f"Found: {name}")

            result = await mesh.call("lookup", "alice")
            assert result["reply"] == "Found: alice"

    async def test_mixed_model_input_scalar_output(self):
        """BaseModel input with scalar output works."""
        spec = AgentSpec(name="length", description="Returns message length")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def length(req: EchoInput) -> int:
                return len(req.message)

            result = await mesh.call("length", {"message": "hello"})
            assert result == 5
