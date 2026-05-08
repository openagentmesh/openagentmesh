"""Handler shape inspection for the @mesh.agent decorator (ADR-0031, ADR-0046, ADR-0052)."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Literal, get_args, get_origin, get_type_hints

from pydantic import BaseModel, TypeAdapter

from ._context import KVEntry
from ._sources import MeshMessage


SourceParamKind = Literal["kv_entry", "mesh_message", "model", "bytes", "none"]


@dataclass
class HandlerInfo:
    """Result of inspecting a handler function."""

    func: Any
    input_adapter: TypeAdapter | None
    output_adapter: TypeAdapter | None
    invocable: bool
    streaming: bool
    source_param_kind: SourceParamKind = "none"
    source_param_model: type | None = None  # T for KVEntry[T] / MeshMessage[T] / Model


def _classify_source_param(annot: Any) -> tuple[SourceParamKind, type | None]:
    """Classify a handler parameter annotation for source dispatch (ADR-0052).

    Returns (kind, payload_model_cls). For ``KVEntry[T]`` / ``MeshMessage[T]``
    the model class is the inner ``T``; for a bare Pydantic model it's the
    annotation itself; for ``bytes`` the class is None.
    """
    if annot is None:
        return ("none", None)

    origin = get_origin(annot)
    args = get_args(annot)

    base = origin if origin is not None else annot
    if base is KVEntry:
        inner = args[0] if args else None
        return ("kv_entry", inner)
    if base is MeshMessage:
        inner = args[0] if args else None
        return ("mesh_message", inner)
    if annot is bytes:
        return ("bytes", None)
    if isinstance(annot, type) and issubclass(annot, BaseModel):
        return ("model", annot)
    return ("none", None)


def inspect_handler(func: Any) -> HandlerInfo:
    """Inspect an async handler to determine capabilities and type models.

    Rules (ADR-0031, ADR-0042, ADR-0043, ADR-0046, ADR-0052):
    - async def with request param and return   -> invocable=True,  streaming=False
    - async generator with request param        -> invocable=True,  streaming=True
    - async def without request param, returns  -> invocable=True,  streaming=False (trigger)
    - async generator without request param     -> invocable=False, streaming=True  (publisher)
    - async def without request param, no return -> invocable=False, streaming=False (watcher)

    A handler whose first parameter is annotated as ``KVEntry`` or ``MeshMessage``
    is source-driven: invocable is False (the runtime cannot synthesize the
    envelope from a wire payload). Sources provide the trigger; ``mesh.call``
    is unavailable for these agents.

    Type hints for non-envelope parameters can be any type Pydantic's
    TypeAdapter supports (ADR-0046).
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

    source_kind: SourceParamKind = "none"
    source_model: type | None = None
    input_adapter: TypeAdapter | None = None
    if params:
        param_type = hints.get(params[0].name)
        source_kind, source_model = _classify_source_param(param_type)
        if source_kind in ("kv_entry", "mesh_message"):
            # Envelope inputs are dispatcher-built; no TypeAdapter for the param.
            input_adapter = None
        elif param_type is not None:
            input_adapter = TypeAdapter(param_type)

    output_adapter: TypeAdapter | None = None
    return_type = hints.get("return")
    if return_type is not None and return_type is not type(None):
        output_adapter = TypeAdapter(return_type)

    if source_kind in ("kv_entry", "mesh_message"):
        invocable = False
    else:
        invocable = (
            input_adapter is not None
            or (output_adapter is not None and not streaming)
        )

    return HandlerInfo(
        func=func,
        input_adapter=input_adapter,
        output_adapter=output_adapter,
        invocable=invocable,
        streaming=streaming,
        source_param_kind=source_kind,
        source_param_model=source_model,
    )
