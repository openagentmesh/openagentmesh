"""Retry, fallback, and error monitoring patterns for flaky agents."""

import asyncio
import random

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, MeshError


class SummarizeInput(BaseModel):
    text: str


class SummarizeOutput(BaseModel):
    summary: str


async def call_with_retry(mesh: AgentMesh, agent: str, payload, retries: int = 3, base_delay: float = 0.1):
    for attempt in range(retries):
        try:
            return await mesh.call(agent, payload)
        except MeshError as e:
            if e.code == "not_found":
                raise
            if attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"  Attempt {attempt + 1} failed ({e.code}), retrying in {delay}s")
            await asyncio.sleep(delay)


async def call_with_fallback(mesh: AgentMesh, agents: list[str], payload):
    last_error = None
    for agent in agents:
        try:
            return await mesh.call(agent, payload, timeout=5.0)
        except MeshError as e:
            last_error = e
            print(f"  {agent} failed ({e.code}), trying next...")
            if e.code in ("not_found", "handler_error"):
                continue
            raise
    raise last_error


async def main(mesh: AgentMesh) -> None:
    @mesh.agent(AgentSpec(name="nlp.summarizer", description="Summarizes text. May fail under load."))
    async def summarize(req: SummarizeInput) -> SummarizeOutput:
        if random.random() < 0.3:
            raise RuntimeError("LLM provider timeout")
        return SummarizeOutput(summary=f"Summary of: {req.text[:50]}")

    @mesh.agent(AgentSpec(name="nlp.basic-summarizer", description="Simple fallback summarizer."))
    async def basic_summarize(req: SummarizeInput) -> SummarizeOutput:
        return SummarizeOutput(summary=req.text[:80] + "...")

    # Pattern 1: Basic error handling
    print("--- Pattern 1: Basic error handling ---")
    try:
        result = await mesh.call("nlp.summarizer", SummarizeInput(text="Long document about AI agents"))
        print(f"  Success: {result['summary']}")
    except MeshError as e:
        print(f"  Error: [{e.code}] {e}")

    # Pattern 2: Retry with backoff
    print("\n--- Pattern 2: Retry with backoff ---")
    result = await call_with_retry(mesh, "nlp.summarizer", SummarizeInput(text="Important document"))
    print(f"  Success: {result['summary']}")

    # Pattern 3: Fallback agent
    print("\n--- Pattern 3: Fallback to alternative agent ---")
    result = await call_with_fallback(
        mesh,
        agents=["nlp.summarizer", "nlp.basic-summarizer"],
        payload=SummarizeInput(text="Critical document that must be processed"),
    )
    print(f"  Success: {result['summary']}")
