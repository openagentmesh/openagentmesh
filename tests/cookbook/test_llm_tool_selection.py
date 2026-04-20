"""Tests for the LLM-driven tool selection cookbook recipe."""

import json

import pytest

from openagentmesh import AgentMesh
from openagentmesh.demos.llm_tool_selection import TaskRequest, main


class TestLLMToolSelectionRecipe:
    async def test_main_completes(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)

    async def test_orchestrator_selects_summarizer_for_summarize_task(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)
            result = await mesh.call(
                "orchestrator", TaskRequest(task="Summarize the document")
            )
            answer = json.loads(result["answer"])
            assert "summary" in answer

    async def test_orchestrator_falls_back_for_unknown_task(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)
            result = await mesh.call(
                "orchestrator", TaskRequest(task="Do something unrelated")
            )
            assert "answer" in result
