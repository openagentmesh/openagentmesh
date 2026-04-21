"""Handler shape inspection for the @mesh.agent decorator (ADR-0031, ADR-0046)."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import TypeAdapter


@dataclass
class HandlerInfo:
    """Result of inspecting a handler function."""

    func: Any
    input_adapter: TypeAdapter | None
    output_adapter: TypeAdapter | None
    invocable: bool
    streaming: bool


def inspect_handler(func: Any) -> HandlerInfo:
    """Inspect an async handler to determine capabilities and type models.

    Rules (ADR-0031, ADR-0042, ADR-0043, ADR-0046):
    - async def with request param and return   -> invocable=True,  streaming=False
    - async generator with request param        -> invocable=True,  streaming=True
    - async def without request param, returns  -> invocable=True,  streaming=False (trigger)
    - async generator without request param     -> invocable=False, streaming=True  (publisher)
    - async def without request param, no return -> invocable=False, streaming=False (watcher)

    Type hints can be any type Pydantic's TypeAdapter supports (ADR-0046):
    BaseModel subclasses, scalars (str, int, float, bool), generics (list[X],
    dict[str, X]), Optional, Union, Literal, Enum, datetime, UUID, etc.
    """
    if not (inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func)):
        raise TypeError(
            f"Handler '{func.__name__}' must be async (async def). "
            f"Got {type(func).__name__}."
        )

    streaming = inspect.isasyncgenfunction(func)
    hints = get_type_hints(func)

    sig = inspect.signature(func)
    params = [p for name, p in sig.parameters.items() if name != "self"]

    input_adapter: TypeAdapter | None = None
    if params:
        param_type = hints.get(params[0].name)
        if param_type is not None:
            input_adapter = TypeAdapter(param_type)

    output_adapter: TypeAdapter | None = None
    return_type = hints.get("return")
    if return_type is not None and return_type is not type(None):
        output_adapter = TypeAdapter(return_type)

    invocable = input_adapter is not None or (output_adapter is not None and not streaming)

    return HandlerInfo(
        func=func,
        input_adapter=input_adapter,
        output_adapter=output_adapter,
        invocable=invocable,
        streaming=streaming,
    )
