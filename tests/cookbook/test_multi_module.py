"""Tests for the multi-module cookbook recipe (docs/cookbook/multi-module.md).

Exercises the documented split-into-modules pattern: importing an agent module
registers its handler on the shared mesh instance as a side effect, and
``mesh.local()`` (instance method) connects that instance without re-registering.
"""

from openagentmesh.demos.multimodule import agents  # noqa: F401  (import registers agents)
from openagentmesh.demos.multimodule.agents import researcher, summarizer  # noqa: F401
from openagentmesh.demos.multimodule.mesh import mesh


class TestMultiModuleRecipe:
    async def test_researcher_registered_by_import(self):
        async with mesh.local():
            result = await mesh.call("analysts.researcher", {"topic": "NATS"})
            assert "NATS" in result["findings"]

    async def test_both_agent_modules_share_one_mesh(self):
        async with mesh.local():
            catalog = await mesh.catalog()
            names = {entry.name for entry in catalog}
            assert {"analysts.researcher", "nlp.summarizer"} <= names

            result = await mesh.call(
                "nlp.summarizer",
                summarizer.SummarizeInput(text="AgentMesh connects agents over NATS.", max_length=9),
            )
            assert result["summary"] == "AgentMesh"
