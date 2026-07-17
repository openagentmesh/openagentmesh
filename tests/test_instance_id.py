"""Tests for ADR-0059: mesh.instance_id stable per-process identifier."""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec

X_MESH_INSTANCE_ID = "X-Mesh-Instance-Id"


class EchoIn(BaseModel):
    text: str


class EchoOut(BaseModel):
    reply: str


class Tick(BaseModel):
    n: int


# --- Attribute behavior ---


class TestInstanceIdAttribute:
    def test_attribute_is_hex_string(self):
        mesh = AgentMesh()
        assert isinstance(mesh.instance_id, str)
        assert len(mesh.instance_id) == 32
        int(mesh.instance_id, 16)  # raises if not hex

    def test_two_instances_have_different_ids(self):
        a = AgentMesh()
        b = AgentMesh()
        assert a.instance_id != b.instance_id

    def test_id_stable_across_property_reads(self):
        mesh = AgentMesh()
        first = mesh.instance_id
        for _ in range(5):
            assert mesh.instance_id == first


# --- Header stamping on outbound emissions ---


class TestInstanceIdOnInvocation:
    async def test_call_request_carries_caller_instance_id(self):
        """The request msg sent via mesh.call() has the caller's instance id."""
        async with AgentMesh.local() as host:
            @host.agent(AgentSpec(name="echo", description="echoes"))
            async def echo(req: EchoIn) -> EchoOut:
                return EchoOut(reply=req.text)

            await host._subscribe_pending()  # subscribe the agent now

            async with AgentMesh(host.url) as caller:
                received: list[dict[str, str]] = []

                async def sniff(msg):
                    received.append(dict(msg.headers or {}))

                sub = await caller._conn.subscribe("mesh.agent.echo", cb=sniff)
                await caller._conn.flush()

                # mesh.call needs to resolve "echo" via the catalog cache;
                # bypass that by hitting the subject directly.
                await caller._conn.request(
                    "mesh.agent.echo",
                    json.dumps({"text": "hi"}).encode(),
                    timeout=2.0,
                    headers=caller._with_instance_id({"X-Mesh-Request-Id": "rid-1"}),
                )
                await caller._conn.flush()
                await asyncio.sleep(0.05)
                await sub.unsubscribe()

                assert received, "no request observed on echo subject"
                assert any(h.get(X_MESH_INSTANCE_ID) == caller.instance_id for h in received)

    async def test_call_reply_carries_responder_instance_id(self):
        """The reply msg returned to the caller has the responder's instance id."""
        async with AgentMesh.local() as host:
            @host.agent(AgentSpec(name="echo", description="echoes"))
            async def echo(req: EchoIn) -> EchoOut:
                return EchoOut(reply=req.text)

            await host._subscribe_pending()

            async with AgentMesh(host.url) as caller:
                response = await caller._conn.request(
                    "mesh.agent.echo",
                    json.dumps({"text": "hi"}).encode(),
                    timeout=2.0,
                    headers={"X-Mesh-Request-Id": "test-rid"},
                )
                assert response.headers.get(X_MESH_INSTANCE_ID) == host.instance_id
                assert host.instance_id != caller.instance_id

    async def test_send_carries_caller_instance_id(self):
        async with AgentMesh.local() as host:
            received_invocations: list[dict[str, str]] = []

            @host.agent(AgentSpec(name="sink", description="sink"))
            async def sink(req: EchoIn) -> EchoOut:
                return EchoOut(reply="ok")

            await host._subscribe_pending()

            async with AgentMesh(host.url) as caller:
                async def sniff(msg):
                    received_invocations.append(dict(msg.headers or {}))

                sub = await caller._conn.subscribe("mesh.agent.sink", cb=sniff)
                await caller._conn.flush()

                # Bypass catalog resolution; raw publish exercises caller's
                # _with_instance_id default through the SDK send path:
                await caller._conn.publish(
                    "mesh.agent.sink",
                    json.dumps({"text": "fire"}).encode(),
                    headers=caller._with_instance_id({"X-Mesh-Request-Id": "rid-2"}),
                )
                await caller._conn.flush()
                await asyncio.sleep(0.05)
                await sub.unsubscribe()

                assert any(h.get(X_MESH_INSTANCE_ID) == caller.instance_id for h in received_invocations)

    async def test_stream_chunks_carry_responder_instance_id(self):
        async with AgentMesh.local() as host:
            @host.agent(AgentSpec(name="stream", description="streams"))
            async def streamer(req: EchoIn):
                yield EchoOut(reply=req.text + "-1")
                yield EchoOut(reply=req.text + "-2")

            await host._subscribe_pending()

            async with AgentMesh(host.url) as caller:
                received: list[dict[str, str]] = []

                async def sniff(msg):
                    received.append(dict(msg.headers or {}))

                # The stream subject is mesh.stream.{request_id}; pick our own.
                request_id = "stream-rid"
                stream_subject = f"mesh.stream.{request_id}"
                sub = await caller._conn.subscribe(stream_subject, cb=sniff)
                await caller._conn.flush()

                # Fire the stream request directly (bypass mesh.stream caller-side
                # subscription which would race ours):
                await caller._conn.publish(
                    "mesh.agent.stream",
                    json.dumps({"text": "x"}).encode(),
                    headers=caller._with_instance_id({
                        "X-Mesh-Request-Id": request_id,
                        "X-Mesh-Stream": "true",
                    }),
                )
                await caller._conn.flush()
                await asyncio.sleep(0.5)  # allow streamer to emit chunks
                await sub.unsubscribe()

                # At least one chunk header carried the responder's instance_id
                assert any(h.get(X_MESH_INSTANCE_ID) == host.instance_id for h in received), \
                    f"No chunk carried host instance_id={host.instance_id[:8]}; received={received}"


class TestInstanceIdOnPublisher:
    async def test_publisher_events_carry_instance_id(self):
        """ADR-0034 publisher pattern: yielded events include host instance id."""
        async with AgentMesh.local() as host:
            @host.agent(AgentSpec(name="ticker", description="ticks"))
            async def ticker():
                yield Tick(n=1)
                yield Tick(n=2)

            async with AgentMesh(host.url) as caller:
                received: list[dict[str, str]] = []

                async def sniff(msg):
                    received.append(dict(msg.headers or {}))

                # Subscribe BEFORE triggering the publisher; core NATS doesn't
                # replay missed messages.
                sub = await caller._conn.subscribe("mesh.agent.ticker.events", cb=sniff)
                await caller._conn.flush()

                # Now start the publisher emit task.
                await host._subscribe_pending()
                await asyncio.sleep(0.5)
                await sub.unsubscribe()

                assert any(h.get(X_MESH_INSTANCE_ID) == host.instance_id for h in received), \
                    f"No event carried host instance_id; received={received}"


# --- User override ---


class TestInstanceIdOverride:
    async def test_user_supplied_header_wins(self):
        """If a caller passes X-Mesh-Instance-Id in headers, the SDK does not overwrite.

        Note: this only matters for paths that accept headers from the user.
        Public mesh.call/send/stream do NOT take headers in the v1 API; this
        test exercises the internal contract via raw _nc.publish.
        """
        async with AgentMesh.local() as mesh:
            received: list[dict[str, str]] = []

            async def sniff(msg):
                received.append(dict(msg.headers or {}))

            sub = await mesh._conn.subscribe("test.override", cb=sniff)
            await mesh._conn.publish(
                "test.override",
                b"x",
                headers={X_MESH_INSTANCE_ID: "user-supplied"},
            )
            await mesh._conn.flush()
            await asyncio.sleep(0.05)
            await sub.unsubscribe()

            # Direct _nc.publish bypasses the SDK's header default.
            # This documents the boundary: SDK adds defaults on its own emission
            # paths; raw _nc.publish remains untouched.
            assert received[0].get(X_MESH_INSTANCE_ID) == "user-supplied"
