"""Tests for mesh.send() with on_reply/on_error callbacks (ADR-0034)."""

import asyncio

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, MeshError, MeshTimeout


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    reply: str


class TestSendOnReply:
    async def test_on_reply_receives_response(self):
        """on_reply callback fires with the agent's response."""
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="echo", description="Echo"))
            async def echo(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=f"Echo: {req.message}")

            received = []

            async def on_reply(result: dict):
                received.append(result)

            await mesh.send(
                "echo",
                {"message": "hello"},
                on_reply=on_reply,
                timeout=5.0,
            )

            # Wait for the background callback to fire
            for _ in range(50):
                if received:
                    break
                await asyncio.sleep(0.05)

            assert len(received) == 1
            assert received[0]["reply"] == "Echo: hello"

    async def test_on_reply_and_reply_to_mutually_exclusive(self):
        """Passing both on_reply and reply_to raises ValueError."""
        async with AgentMesh.local() as mesh:
            with pytest.raises(ValueError, match="mutually exclusive"):
                await mesh.send(
                    "echo",
                    {},
                    on_reply=lambda r: None,
                    reply_to="some.subject",
                )

    async def test_fire_and_forget_still_works(self):
        """send() without on_reply or reply_to still works (no callback)."""
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="sink", description="Sink"))
            async def sink(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply="ok")

            # Should not raise
            await mesh.send("sink", {"message": "fire"})

    async def test_reply_to_still_works(self):
        """send() with reply_to= (legacy) still publishes with that reply subject."""
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="echo2", description="Echo"))
            async def echo2(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=req.message)

            reply_subject = "test.reply.123"
            received = []

            async def catcher():
                async for msg in mesh.subscribe(subject=reply_subject, timeout=2.0):
                    received.append(msg)
                    break

            async def sender():
                await asyncio.sleep(0.05)
                await mesh.send("echo2", {"message": "hi"}, reply_to=reply_subject)

            await asyncio.gather(
                asyncio.wait_for(catcher(), timeout=5.0),
                sender(),
            )

            assert received[0]["reply"] == "hi"


class TestSendOnError:
    async def test_on_error_on_timeout(self):
        """on_error fires with MeshTimeout when no reply arrives."""
        async with AgentMesh.local() as mesh:
            errors = []

            async def on_reply(result: dict):
                pass

            async def on_error(err: MeshError):
                errors.append(err)

            await mesh.send(
                "nonexistent-agent",
                {"message": "hello"},
                on_reply=on_reply,
                on_error=on_error,
                timeout=0.3,
            )

            # Wait for timeout to fire
            for _ in range(20):
                if errors:
                    break
                await asyncio.sleep(0.05)

            assert len(errors) == 1
            assert isinstance(errors[0], MeshTimeout)

    async def test_on_error_on_handler_error(self):
        """on_error fires with MeshError when handler raises."""
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="failing", description="Fails"))
            async def failing(req: EchoInput) -> EchoOutput:
                raise ValueError("handler boom")

            errors = []
            replies = []

            async def on_reply(result: dict):
                replies.append(result)

            async def on_error(err: MeshError):
                errors.append(err)

            await mesh.send(
                "failing",
                {"message": "hello"},
                on_reply=on_reply,
                on_error=on_error,
                timeout=5.0,
            )

            for _ in range(50):
                if errors:
                    break
                await asyncio.sleep(0.05)

            assert len(errors) == 1
            assert "handler boom" in str(errors[0])
            assert len(replies) == 0

    async def test_no_on_error_logs_warning(self):
        """Without on_error, timeout logs a warning (no crash)."""
        async with AgentMesh.local() as mesh:
            received = []

            async def on_reply(result: dict):
                received.append(result)

            await mesh.send(
                "nonexistent",
                {},
                on_reply=on_reply,
                timeout=0.3,
            )

            await asyncio.sleep(0.5)
            assert len(received) == 0
