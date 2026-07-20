"""Model backends for the persona-team experiment.

``StubModel`` is deterministic and offline: it exercises the coordination
machinery and the usage-metering plumbing. Its token numbers are SYNTHETIC
and must never be presented as experiment results. Measured runs use
``OpenRouterModel`` (requires OPENROUTER_API_KEY).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Protocol

from pydantic import BaseModel

from .records import Decision

# Synthesis prompts embed this marker so structured-output paths are
# distinguishable; StubModel keys on it to return a JSON decision.
SYNTHESIZE_MARKER = "Return a single JSON object"


class ModelReply(BaseModel):
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "stub"


class ChatModel(Protocol):
    async def complete(self, system: str, prompt: str) -> ModelReply: ...


def split_reply(text: str) -> tuple[str, str]:
    """Split a position reply into (claim, rationale): first line vs. rest."""
    first, _, rest = text.strip().partition("\n")
    return first.strip(), rest.strip()


def parse_decision(
    text: str, task_id: str, synthesized_by: str, converged_early: bool
) -> Decision:
    """Parse a synthesis reply into a Decision; fall back to freeform text."""
    try:
        data = json.loads(text)
        return Decision(
            task_id=task_id,
            recommendation=str(data.get("recommendation", "")) or text.strip(),
            alternatives=[str(a) for a in data.get("alternatives", [])],
            risks=[str(r) for r in data.get("risks", [])],
            rationale=str(data.get("rationale", "")),
            synthesized_by=synthesized_by,
            converged_early=converged_early,
        )
    except (json.JSONDecodeError, AttributeError):
        return Decision(
            task_id=task_id,
            recommendation=text.strip(),
            synthesized_by=synthesized_by,
            converged_early=converged_early,
        )


class StubModel:
    """Deterministic canned model for dry runs.

    Position replies vary per call up to ``converge_after`` revisions, then
    freeze — letting tests drive the convergence check. Token counts are
    derived from prompt/reply length: synthetic by construction.
    """

    def __init__(self, converge_after: int | None = None):
        self._converge_after = converge_after
        self._calls: dict[str, int] = {}

    async def complete(self, system: str, prompt: str) -> ModelReply:
        lens = hashlib.sha256(system.encode()).hexdigest()[:8]

        if SYNTHESIZE_MARKER in prompt:
            text = json.dumps({
                "recommendation": f"Stub recommendation from lens {lens}.",
                "alternatives": ["stub alternative"],
                "risks": ["stub risk"],
                "rationale": "Deterministic stub synthesis; not a real deliberation.",
            })
        else:
            n = self._calls.get(system, 0) + 1
            self._calls[system] = n
            # call 1 = initial position, call k+1 = k-th revision; freeze
            # after converge_after revisions so positions stop changing
            effective = n
            if self._converge_after is not None:
                effective = min(n, self._converge_after + 1)
            text = (
                f"Position v{effective} from lens {lens}\n"
                f"Deterministic stub rationale for revision {effective}."
            )

        return ModelReply(
            text=text,
            input_tokens=len(prompt.split()) + len(system.split()),
            output_tokens=len(text.split()),
            model="stub",
        )


class OpenRouterModel:
    """Real LLM calls through OpenRouter (openai client, e.g. anthropic/* slugs).

    Requires the ``openai`` package and OPENROUTER_API_KEY. This is the only
    backend that produces reportable experiment numbers.
    """

    def __init__(
        self,
        slug: str,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Measured experiment runs need it; "
                "use StubModel for dry runs of the machinery."
            )
        try:
            # openai is deliberately not a project dependency: this demo-only
            # backend imports it lazily and fails with instructions instead.
            from openai import AsyncOpenAI  # ty: ignore[unresolved-import]
        except ImportError as e:
            raise RuntimeError(
                "The 'openai' package is required for OpenRouter runs: pip install openai"
            ) from e
        self._slug = slug
        self._client = AsyncOpenAI(base_url=base_url, api_key=key)

    async def complete(self, system: str, prompt: str) -> ModelReply:
        response = await self._client.chat.completions.create(
            model=self._slug,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        usage = response.usage
        return ModelReply(
            text=response.choices[0].message.content or "",
            input_tokens=(usage.prompt_tokens or 0) if usage else 0,
            output_tokens=(usage.completion_tokens or 0) if usage else 0,
            model=self._slug,
        )
