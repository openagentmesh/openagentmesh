"""Tests for the reactive-pipeline cookbook recipe (KV watch coordination)."""

import json

import pytest

from openagentmesh import AgentMesh
from openagentmesh.demos.reactive_pipeline import Document, Extracted, Summary, main


class TestReactivePipelineRecipe:
    async def test_main_completes(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)

    async def test_pipeline_produces_summary(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)
            raw = await mesh.kv.get("pipeline.doc-001.summary")
            summary = Summary.model_validate_json(raw)
            assert summary.id == "doc-001"
            assert summary.entity_count > 0

    async def test_pipeline_produces_extracted(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)
            raw = await mesh.kv.get("pipeline.doc-001.extracted")
            extracted = Extracted.model_validate_json(raw)
            assert extracted.word_count > 0
            assert len(extracted.entities) > 0
