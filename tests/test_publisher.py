"""Tests for publisher agent emission (ADR-0034)."""

import asyncio

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, MeshError


class PriceEvent(BaseModel):
    symbol: str
    price: float


class TestPublisherEmission:
    async def test_publisher_emits_to_event_subject(self):
        """Publisher handler's yielded values arrive on mesh.subscribe(agent=...)."""
        async with AgentMesh.local() as mesh:
            spec = AgentSpec(
                name="ticker",
                channel="finance",
                description="Emits prices",
            )

            prices = [100.0, 101.0, 102.0]

            @mesh.agent(spec)
            async def ticker() -> PriceEvent:
                for p in prices:
                    yield PriceEvent(symbol="AAPL", price=p)

            received = []
            async for event in mesh.subscribe(agent="ticker", timeout=2.0):
                received.append(event["price"])
                if len(received) == 3:
                    break

            assert received == [100.0, 101.0, 102.0]

    async def test_publisher_terminal_on_generator_exit(self):
        """When publisher generator returns, terminal message closes subscribers."""
        async with AgentMesh.local() as mesh:
            spec = AgentSpec(name="finite", description="Emits two events")

            @mesh.agent(spec)
            async def finite() -> PriceEvent:
                yield PriceEvent(symbol="A", price=1.0)
                yield PriceEvent(symbol="B", price=2.0)

            received = []
            async for event in mesh.subscribe(agent="finite", timeout=2.0):
                received.append(event["symbol"])

            assert received == ["A", "B"]

    async def test_publisher_error_propagates_to_subscriber(self):
        """Generator error sends error message to subscribers."""
        async with AgentMesh.local() as mesh:
            spec = AgentSpec(name="failing-pub", description="Fails after one event")

            @mesh.agent(spec)
            async def failing_pub() -> PriceEvent:
                yield PriceEvent(symbol="OK", price=1.0)
                raise ValueError("publisher crashed")

            received = []
            with pytest.raises(MeshError, match="publisher crashed"):
                async for event in mesh.subscribe(agent="failing-pub", timeout=2.0):
                    received.append(event)

            assert len(received) == 1

    async def test_publisher_not_invocable(self):
        """Publisher agents are not invocable; catalog shows invocable=False."""
        async with AgentMesh.local() as mesh:
            spec = AgentSpec(name="pub-only", description="Publisher")

            @mesh.agent(spec)
            async def pub_only() -> PriceEvent:
                yield PriceEvent(symbol="X", price=0.0)

            catalog = await mesh.catalog()
            entry = [e for e in catalog if e.name == "pub-only"][0]
            assert entry.invocable is False
            assert entry.streaming is True
