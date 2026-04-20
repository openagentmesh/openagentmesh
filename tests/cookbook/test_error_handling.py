"""Tests for the error-handling cookbook recipe (retry, fallback patterns)."""

import random

import pytest

from openagentmesh import AgentMesh, AgentSpec, MeshError
from openagentmesh.demos.error_handling import (
    SummarizeInput,
    SummarizeOutput,
    call_with_fallback,
    call_with_retry,
)


class TestRetryPattern:
    async def test_retry_succeeds_when_agent_recovers(self):
        async with AgentMesh.local() as mesh:
            random.seed(42)

            @mesh.agent(AgentSpec(name="flaky", description="Fails sometimes"))
            async def flaky(req: SummarizeInput) -> SummarizeOutput:
                if random.random() < 0.3:
                    raise RuntimeError("transient")
                return SummarizeOutput(summary=req.text[:20])

            result = await call_with_retry(mesh, "flaky", SummarizeInput(text="test input"))
            assert "summary" in result

    async def test_retry_raises_on_no_responders(self):
        async with AgentMesh.local() as mesh:
            from nats.errors import NoRespondersError

            with pytest.raises(NoRespondersError):
                await call_with_retry(mesh, "nonexistent", SummarizeInput(text="x"))


class TestFallbackPattern:
    async def test_fallback_uses_second_agent_when_first_fails(self):
        async with AgentMesh.local() as mesh:

            @mesh.agent(AgentSpec(name="broken", description="Always fails"))
            async def broken(req: SummarizeInput) -> SummarizeOutput:
                raise RuntimeError("permanently broken")

            @mesh.agent(AgentSpec(name="reliable", description="Always works"))
            async def reliable(req: SummarizeInput) -> SummarizeOutput:
                return SummarizeOutput(summary="fallback result")

            result = await call_with_fallback(
                mesh, ["broken", "reliable"], SummarizeInput(text="test")
            )
            assert result["summary"] == "fallback result"


class TestFullRecipe:
    async def test_main_completes_with_seeded_random(self):
        async with AgentMesh.local() as mesh:
            random.seed(0)
            from openagentmesh.demos.error_handling import main
            await main(mesh)
