"""Tests for the load-balancing cookbook recipe (queue group distribution)."""

import asyncio

import pytest

from openagentmesh import AgentMesh
from openagentmesh.demos.load_balancing import TranslateInput, main


class TestLoadBalancingRecipe:
    async def test_main_completes(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)

    async def test_all_requests_get_responses(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)
            tasks = [
                mesh.call("nlp.translator", TranslateInput(text=f"msg {i}"))
                for i in range(5)
            ]
            results = await asyncio.gather(*tasks)
            assert len(results) == 5
            assert all("translated" in r for r in results)
            assert all("handled_by" in r for r in results)
