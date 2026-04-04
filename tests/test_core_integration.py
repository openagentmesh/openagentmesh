"""Integration tests for AgentMesh — requires local NATS (via EmbeddedNatsServer)."""

import asyncio

import pytest
from pydantic import BaseModel

from agentmesh import AgentMesh
from agentmesh.errors import MeshError


class Req(BaseModel):
    value: str


class Resp(BaseModel):
    result: str


# --- mesh.register() imperative API ---


@pytest.mark.asyncio
async def test_register_imperative_api(mesh: AgentMesh):
    async def echo(req: Req) -> Resp:
        return Resp(result=req.value)

    mesh.register(name="echo", handler=echo, description="Echoes the input.")
    result = await mesh.call("echo", {"value": "hello"})
    assert result == {"result": "hello"}


@pytest.mark.asyncio
async def test_register_appears_in_catalog(mesh: AgentMesh):
    async def echo(req: Req) -> Resp:
        return Resp(result=req.value)

    mesh.register(name="echo", handler=echo, description="Echoes.")
    catalog = await mesh.catalog()
    assert any(e.name == "echo" for e in catalog)


# --- mesh.discover() ---


@pytest.mark.asyncio
async def test_discover_returns_full_contracts(mesh: AgentMesh):
    @mesh.agent(name="alpha", description="Alpha agent.")
    async def alpha(req: Req) -> Resp:
        return Resp(result="a")

    contracts = await mesh.discover()
    assert len(contracts) == 1
    assert contracts[0].name == "alpha"
    assert contracts[0].input_schema != {}
    assert contracts[0].output_schema != {}


@pytest.mark.asyncio
async def test_discover_filters_by_channel(mesh: AgentMesh):
    @mesh.agent(name="nlp-agent", channel="nlp")
    async def nlp(req: Req) -> Resp:
        return Resp(result="nlp")

    @mesh.agent(name="finance-agent", channel="finance")
    async def finance(req: Req) -> Resp:
        return Resp(result="fin")

    contracts = await mesh.discover(channel="nlp")
    assert len(contracts) == 1
    assert contracts[0].name == "nlp-agent"


@pytest.mark.asyncio
async def test_discover_filters_by_tags(mesh: AgentMesh):
    @mesh.agent(name="tagger", tags=["text", "summarization"])
    async def tagger(req: Req) -> Resp:
        return Resp(result="tagged")

    @mesh.agent(name="other")
    async def other(req: Req) -> Resp:
        return Resp(result="other")

    contracts = await mesh.discover(tags=["summarization"])
    assert len(contracts) == 1
    assert contracts[0].name == "tagger"


# --- mesh.catalog() filtering ---


@pytest.mark.asyncio
async def test_catalog_filters_by_channel(mesh: AgentMesh):
    @mesh.agent(name="a", channel="ch1")
    async def a(req: Req) -> Resp:
        return Resp(result="a")

    @mesh.agent(name="b", channel="ch2")
    async def b(req: Req) -> Resp:
        return Resp(result="b")

    result = await mesh.catalog(channel="ch1")
    assert len(result) == 1
    assert result[0].name == "a"


@pytest.mark.asyncio
async def test_catalog_filters_by_tags(mesh: AgentMesh):
    @mesh.agent(name="tagged", tags=["alpha", "beta"])
    async def tagged(req: Req) -> Resp:
        return Resp(result="t")

    @mesh.agent(name="plain")
    async def plain(req: Req) -> Resp:
        return Resp(result="p")

    result = await mesh.catalog(tags=["alpha"])
    assert len(result) == 1
    assert result[0].name == "tagged"


# --- mesh.contract() ---


@pytest.mark.asyncio
async def test_contract_returns_full_contract(mesh: AgentMesh):
    @mesh.agent(name="inspector", description="Inspect this.")
    async def inspector(req: Req) -> Resp:
        return Resp(result="ok")

    contract = await mesh.contract("inspector")
    assert contract.name == "inspector"
    assert contract.description == "Inspect this."
    assert "value" in contract.input_schema["properties"]


@pytest.mark.asyncio
async def test_contract_raises_for_unknown_agent(mesh: AgentMesh):
    with pytest.raises(MeshError) as exc_info:
        await mesh.contract("ghost")
    assert exc_info.value.code == "not_found"


# --- mesh.send() async callback ---


@pytest.mark.asyncio
async def test_send_delivers_to_reply_subject(mesh: AgentMesh):
    """mesh.send() publishes to the agent; the agent replies to the reply_to subject."""

    @mesh.agent(name="replier")
    async def replier(req: Req) -> Resp:
        return Resp(result=f"got:{req.value}")

    reply_subject = "mesh.results.test-send-001"
    event = asyncio.Event()
    received: list[dict] = []

    import json

    async def collect(msg):
        received.append(json.loads(msg.data))
        event.set()

    sub = await mesh._nc.subscribe(reply_subject, cb=collect)
    await mesh._nc.flush()

    await mesh.send("replier", {"value": "ping"}, reply_to=reply_subject)
    await mesh._nc.flush()

    await asyncio.wait_for(event.wait(), timeout=5.0)

    await sub.unsubscribe()
    assert received == [{"result": "got:ping"}]


# --- Channel-namespaced subject routing ---


@pytest.mark.asyncio
async def test_call_routes_via_channel_subject(mesh: AgentMesh):
    @mesh.agent(name="worker", channel="jobs")
    async def worker(req: Req) -> Resp:
        return Resp(result="done")

    result = await mesh.call("worker", {"value": "task"})
    assert result == {"result": "done"}
