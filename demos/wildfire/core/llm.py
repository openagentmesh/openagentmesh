"""Shared structured-output LLM helper for the wildfire LLM peers.

briefer / tasker / narrator all need the same call shape: structured
prompt fields in, one Pydantic-validated model out. This module owns that
pattern so the three agents don't grow three divergent clients:

- ``AsyncOpenAI`` client pointed at OpenRouter, created lazily per process.
  All Claude access goes through OpenRouter's OpenAI-compatible endpoint
  (there is no direct Anthropic dependency); model ids are OpenRouter slugs
  like ``anthropic/claude-sonnet-4.6`` (see ``config.LLM_MODEL_*``).
- Forced tool use: the output model's JSON Schema is presented as a single
  function tool and ``tool_choice`` pins it, so the model must emit
  arguments that parse into the schema. Pydantic validation is the final
  gate; a hallucinated field fails loudly.
- One retry with a short backoff, then :class:`LLMUnavailable`. Callers
  decide the degraded path (briefer: fallback summary; tasker: typed error
  to the caller; narrator: skip the window).

The demo runs without a key: ``OPENROUTER_API_KEY`` unset raises
``LLMUnavailable`` immediately, so every consumer's degraded path is the
no-key path too. Unit tests monkeypatch :func:`structured_llm_call`; they
never hit the network.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TypeVar

from pydantic import BaseModel

_log = logging.getLogger("wildfire.llm")

T = TypeVar("T", bound=BaseModel)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Lazily-created singleton client (per process). ``None`` until first use.
_client = None


class LLMUnavailable(Exception):
    """The LLM call failed (no key, timeout, rate limit, invalid output)."""


def _get_client():
    """Create the OpenRouter client on first use.

    Import is deferred so importing an agent module never requires the
    openai package to be importable in stripped-down environments
    (e.g. docs builds).
    """
    global _client
    if _client is None:
        from openai import AsyncOpenAI

        _client = AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ["OPENROUTER_API_KEY"],
            default_headers={"X-Title": "OpenAgentMesh wildfire demo"},
        )
    return _client


async def structured_llm_call(
    *,
    model: str,
    system: str,
    user_content: str,
    output_model: type[T],
    max_tokens: int = 1024,
    timeout_s: float = 20.0,
) -> T:
    """One structured LLM call returning a validated ``output_model`` instance.

    Raises :class:`LLMUnavailable` on any failure (missing key, network,
    rate limit, schema violation) after one retry. Never returns a
    partially-valid object.
    """
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise LLMUnavailable("OPENROUTER_API_KEY not set")

    tool_name = f"emit_{output_model.__name__.lower()}"
    tool = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": f"Emit the {output_model.__name__} result.",
            "parameters": output_model.model_json_schema(),
        },
    }

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = await asyncio.wait_for(
                _get_client().chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                    tools=[tool],
                    tool_choice={"type": "function", "function": {"name": tool_name}},
                ),
                timeout=timeout_s,
            )
            for call in resp.choices[0].message.tool_calls or []:
                if call.function.name == tool_name:
                    return output_model.model_validate_json(call.function.arguments)
            raise LLMUnavailable("no tool call in response")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 -- every failure maps to the same degraded path
            last_exc = e
            _log.warning("LLM call failed (attempt %d/2, model=%s): %s", attempt + 1, model, e)
            if attempt == 0:
                await asyncio.sleep(1.0)

    raise LLMUnavailable(str(last_exc))
