"""LLM-driven tool selection: discover agents at runtime, no hardcoded tool list."""

import asyncio
import json

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


class SummarizeInput(BaseModel):
    text: str


class SummarizeOutput(BaseModel):
    summary: str


class TranslateInput(BaseModel):
    text: str
    target_language: str = "es"


class TranslateOutput(BaseModel):
    translated: str


class TaskRequest(BaseModel):
    task: str


class TaskResponse(BaseModel):
    answer: str


async def main(mesh: AgentMesh) -> None:
    # Register some tool agents
    @mesh.agent(AgentSpec(name="summarizer", channel="nlp", description="Summarizes text."))
    async def summarize(req: SummarizeInput) -> SummarizeOutput:
        return SummarizeOutput(summary=req.text[:80] + "...")

    @mesh.agent(AgentSpec(name="translator", channel="nlp", description="Translates text to a target language."))
    async def translate(req: TranslateInput) -> TranslateOutput:
        return TranslateOutput(translated=f"[{req.target_language}] {req.text}")

    # Orchestrator discovers and selects agents from the catalog
    @mesh.agent(AgentSpec(name="orchestrator", description="Selects and calls agents based on task description."))
    async def orchestrator(req: TaskRequest) -> TaskResponse:
        # Tier 1: browse catalog (cheap, ~25 tokens per agent)
        catalog = await mesh.catalog()
        invocable = [e for e in catalog if e.invocable and e.name != "orchestrator"]
        print(f"  Catalog: {[e.name for e in invocable]}")

        # Tier 2: select relevant agents (simulated LLM selection)
        selected = [e.name for e in invocable if "summar" in req.task.lower() and "summar" in e.name]
        if not selected:
            selected = [invocable[0].name] if invocable else []
        print(f"  Selected: {selected}")

        # Fetch full contracts for selected agents
        for name in selected:
            contract = await mesh.contract(name)
            print(f"  Contract for {name}: input_schema={json.dumps(contract.input_schema)[:60]}...")

        # Execute (simulated LLM tool call)
        if selected:
            result = await mesh.call(selected[0], {"text": "The quarterly report shows 15% growth."})
            return TaskResponse(answer=json.dumps(result))
        return TaskResponse(answer="No suitable agent found.")

    # Run the orchestrator
    print("Task: 'Summarize the quarterly report'")
    result = await mesh.call("orchestrator", TaskRequest(task="Summarize the quarterly report"))
    print(f"\nResult: {result['answer']}")
