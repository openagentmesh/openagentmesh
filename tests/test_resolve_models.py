"""Unit tests for AgentMesh._resolve_models — no NATS required."""

import pytest
from pydantic import BaseModel

from agentmesh.core import AgentMesh


class Inp(BaseModel):
    x: int


class Out(BaseModel):
    y: str


# --- Happy paths ---


def test_infers_input_and_output_from_type_hints():
    async def handler(req: Inp) -> Out:
        ...

    in_model, out_model = AgentMesh._resolve_models(handler, None, None)
    assert in_model is Inp
    assert out_model is Out


def test_explicit_models_override_hints():
    class AltIn(BaseModel):
        z: float

    class AltOut(BaseModel):
        w: bool

    async def handler(req: Inp) -> Out:
        ...

    in_model, out_model = AgentMesh._resolve_models(handler, AltIn, AltOut)
    assert in_model is AltIn
    assert out_model is AltOut


def test_explicit_input_model_with_inferred_output():
    class AltIn(BaseModel):
        z: float

    async def handler(req: Inp) -> Out:
        ...

    in_model, out_model = AgentMesh._resolve_models(handler, AltIn, None)
    assert in_model is AltIn
    assert out_model is Out


# --- Error paths ---


def test_raises_if_no_parameters():
    async def handler() -> Out:
        ...

    with pytest.raises(ValueError, match="must accept at least one parameter"):
        AgentMesh._resolve_models(handler, None, None)


def test_raises_if_first_param_not_annotated_with_basemodel():
    async def handler(req: str) -> Out:
        ...

    with pytest.raises(ValueError, match="first parameter must be annotated"):
        AgentMesh._resolve_models(handler, None, None)


def test_raises_if_first_param_unannotated():
    async def handler(req) -> Out:
        ...

    with pytest.raises(ValueError, match="first parameter must be annotated"):
        AgentMesh._resolve_models(handler, None, None)


def test_raises_if_return_type_not_basemodel():
    async def handler(req: Inp) -> dict:
        ...

    with pytest.raises(ValueError, match="return type must be annotated"):
        AgentMesh._resolve_models(handler, None, None)


def test_raises_if_no_return_annotation():
    async def handler(req: Inp):
        ...

    with pytest.raises(ValueError, match="return type must be annotated"):
        AgentMesh._resolve_models(handler, None, None)
