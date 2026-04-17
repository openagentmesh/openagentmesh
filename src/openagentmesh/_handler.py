"""Handler shape inspection for the @mesh.agent decorator (ADR-0031)."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import BaseModel


@dataclass
class HandlerInfo:
    """Result of inspecting a handler function."""

    func: Any
    input_model: type[BaseModel] | None
    output_model: type[BaseModel] | None
    invocable: bool
    streaming: bool


def inspect_handler(func: Any) -> HandlerInfo:
    """Inspect an async handler to determine capabilities and type models.

    Rules (ADR-0031):
    - async def with request param and return  -> invocable=True,  streaming=False
    - async generator with request param       -> invocable=True,  streaming=True
    - async generator without request param    -> invocable=False, streaming=True
    """
    if not (inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func)):
        raise TypeError(
            f"Handler '{func.__name__}' must be async (async def). "
            f"Got {type(func).__name__}."
        )

    streaming = inspect.isasyncgenfunction(func)
    hints = get_type_hints(func)

    # Parameters (skip 'self')
    sig = inspect.signature(func)
    params = [p for name, p in sig.parameters.items() if name != "self"]

    # Input model: first parameter with a BaseModel type hint
    input_model: type[BaseModel] | None = None
    if params:
        param_type = hints.get(params[0].name)
        if param_type is not None and isinstance(param_type, type) and issubclass(param_type, BaseModel):
            input_model = param_type

    # Output model: return annotation
    output_model: type[BaseModel] | None = None
    return_type = hints.get("return")
    if return_type is not None and isinstance(return_type, type) and issubclass(return_type, BaseModel):
        output_model = return_type

    invocable = input_model is not None

    if not invocable and not streaming:
        raise TypeError(
            f"Handler '{func.__name__}' has no request parameter and does not yield. "
            f"At least one of invocable or streaming must be true."
        )

    return HandlerInfo(
        func=func,
        input_model=input_model,
        output_model=output_model,
        invocable=invocable,
        streaming=streaming,
    )
