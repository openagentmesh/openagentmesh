"""Tests for the multi-agent cookbook recipe (provider/consumer pattern)."""

import pytest

from openagentmesh import AgentMesh
from openagentmesh.demos.multi_agent import main, SummarizeInput


class TestMultiAgentRecipe:
    async def test_main_completes(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)

    async def test_catalog_contains_summarizer(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)
            catalog = await mesh.catalog()
            names = [e.name for e in catalog]
            assert "nlp.summarizer" in names

    async def test_call_returns_truncated_text(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)
            result = await mesh.call(
                "nlp.summarizer",
                SummarizeInput(text="A" * 300, max_length=50),
            )
            assert len(result["summary"]) == 50
