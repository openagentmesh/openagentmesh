"""Executable twin of docs/cookbook/tracking-llm-usage.md.

Same code as the recipe, wrapped in pytest with AgentMesh.local(). The LLM
client is stubbed — the recipe's `llm_complete` is the reader's own client.
"""

import asyncio
from collections import Counter
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, Usage, report_usage

pytestmark = pytest.mark.asyncio


class Question(BaseModel):
    text: str


class Answer(BaseModel):
    text: str


@dataclass
class _Completion:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


async def llm_complete(text: str) -> _Completion:
    """Stub for the recipe's LLM client."""
    return _Completion(
        text=f"answer to: {text}",
        input_tokens=120,
        output_tokens=40,
        model="stub-model",
    )


async def test_tracking_llm_usage():
    async with AgentMesh.local() as mesh:
        # --- Recipe: report usage from the handler ---
        @mesh.agent(AgentSpec(
            name="support.answerer",
            description="Answers support questions with an LLM. "
                        "Input: question text. Not for order lookups.",
        ))
        async def answerer(req: Question) -> Answer:
            completion = await llm_complete(req.text)
            report_usage(Usage(
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                model=completion.model,
            ))
            return Answer(text=completion.text)

        # --- Recipe: aggregate cost per agent ---
        totals: Counter[str] = Counter()
        seen = asyncio.Event()

        async def cost_monitor(mesh: AgentMesh):
            async for event in mesh.observe.logs():
                if event.event != "usage_reported":
                    continue
                tokens = (
                    event.data.get("input_tokens", 0)
                    + event.data.get("output_tokens", 0)
                )
                totals[event.agent] += tokens
                seen.set()

        monitor = asyncio.create_task(cost_monitor(mesh))
        await asyncio.sleep(0.1)  # let the monitor subscribe

        try:
            result = await mesh.call("support.answerer", {"text": "refund policy?"})
            assert result["text"].startswith("answer to:")

            await asyncio.wait_for(seen.wait(), timeout=5.0)
            assert totals["support.answerer"] == 160  # 120 in + 40 out

            seen.clear()
            await mesh.call("support.answerer", {"text": "shipping times?"})
            await asyncio.wait_for(seen.wait(), timeout=5.0)
            assert totals["support.answerer"] == 320
        finally:
            monitor.cancel()
