"""Tests for ADR-0057: error taxonomy and dedicated `_errors` module.

Covers:
- Class hierarchy and code attributes (InvalidInput, HandlerError, NotFound, ConnectionFailed)
- Public package exports
- Wire envelope round-trip via `from_envelope`
- End-to-end: caller distinguishes InvalidInput from HandlerError
- `mesh.contract(missing)` raises `NotFound` (subclass identity preserved)
- `pydantic.ValidationError` and `openagentmesh.InvalidInput` do not collide
"""

import asyncio

import pytest
from pydantic import BaseModel

from openagentmesh import (
    AgentMesh,
    AgentSpec,
    ChunkSequenceError,
    ConnectionFailed,
    HandlerError,
    InvalidInput,
    InvocationMismatch,
    MeshError,
    MeshTimeout,
    NotFound,
)


class _Input(BaseModel):
    text: str


class _Output(BaseModel):
    result: str


# --- Class hierarchy and codes (unit, no NATS) ---


class TestErrorClassHierarchy:
    def test_invalid_input_is_mesh_error(self):
        err = InvalidInput(agent="x", message="bad payload")
        assert isinstance(err, MeshError)
        assert err.code == "invalid_input"
        assert err.agent == "x"
        assert "bad payload" in err.message

    def test_handler_error_is_mesh_error(self):
        err = HandlerError(agent="x", message="boom")
        assert isinstance(err, MeshError)
        assert err.code == "handler_error"

    def test_not_found_is_mesh_error(self):
        err = NotFound(agent="missing")
        assert isinstance(err, MeshError)
        assert err.code == "not_found"
        assert err.agent == "missing"
        assert "missing" in err.message

    def test_connection_failed_is_mesh_error(self):
        err = ConnectionFailed(message="cannot reach nats")
        assert isinstance(err, MeshError)
        assert err.code == "connection_failed"

    def test_invalid_input_carries_details(self):
        err = InvalidInput(
            agent="scorer",
            details={"errors": [{"loc": ["text"], "msg": "field required", "type": "missing"}]},
        )
        assert err.details["errors"][0]["msg"] == "field required"

    def test_subclass_caught_by_base(self):
        with pytest.raises(MeshError):
            raise InvalidInput(agent="x")
        with pytest.raises(MeshError):
            raise HandlerError(agent="x", message="m")
        with pytest.raises(MeshError):
            raise NotFound(agent="x")

    def test_subclass_caught_by_specific(self):
        with pytest.raises(InvalidInput):
            raise InvalidInput(agent="x")
        with pytest.raises(HandlerError):
            raise HandlerError(agent="x", message="m")
        with pytest.raises(NotFound):
            raise NotFound(agent="x")


# --- Public package exports ---


class TestPublicExports:
    def test_new_classes_exported(self):
        import openagentmesh

        assert openagentmesh.InvalidInput is InvalidInput
        assert openagentmesh.HandlerError is HandlerError
        assert openagentmesh.NotFound is NotFound
        assert openagentmesh.ConnectionFailed is ConnectionFailed

    def test_existing_classes_still_exported(self):
        """Restructure must not break existing imports."""
        import openagentmesh

        assert openagentmesh.MeshError is MeshError
        assert openagentmesh.MeshTimeout is MeshTimeout
        assert openagentmesh.InvocationMismatch is InvocationMismatch
        assert openagentmesh.ChunkSequenceError is ChunkSequenceError

    def test_errors_module_exists(self):
        """Internal _errors module is the single home for exception classes."""
        from openagentmesh import _errors

        assert _errors.MeshError is MeshError
        assert _errors.InvalidInput is InvalidInput
        assert _errors.HandlerError is HandlerError
        assert _errors.NotFound is NotFound
        assert _errors.ConnectionFailed is ConnectionFailed
        assert _errors.MeshTimeout is MeshTimeout
        assert _errors.InvocationMismatch is InvocationMismatch
        assert _errors.ChunkSequenceError is ChunkSequenceError


# --- Pydantic collision check ---


class TestPydanticCollisionAvoidance:
    def test_invalid_input_is_not_pydantic_validation_error(self):
        """InvalidInput must not collide with pydantic.ValidationError."""
        import pydantic

        assert InvalidInput is not pydantic.ValidationError
        assert not issubclass(InvalidInput, pydantic.ValidationError)
        assert not issubclass(pydantic.ValidationError, InvalidInput)


# --- Wire envelope round-trip ---


class TestEnvelopeRoundTrip:
    def test_invalid_input_round_trip(self):
        from openagentmesh._errors import from_envelope

        err = from_envelope({
            "code": "invalid_input",
            "message": "bad payload",
            "agent": "scorer",
            "request_id": "abc",
            "details": {"errors": []},
        })
        assert isinstance(err, InvalidInput)
        assert err.code == "invalid_input"
        assert err.agent == "scorer"
        assert err.request_id == "abc"

    def test_handler_error_round_trip(self):
        from openagentmesh._errors import from_envelope

        err = from_envelope({
            "code": "handler_error",
            "message": "boom",
            "agent": "x",
            "request_id": "r",
            "details": {},
        })
        assert isinstance(err, HandlerError)

    def test_not_found_round_trip(self):
        from openagentmesh._errors import from_envelope

        err = from_envelope({
            "code": "not_found",
            "message": "Agent 'missing' not found",
            "agent": "missing",
            "request_id": "",
            "details": {},
        })
        assert isinstance(err, NotFound)

    def test_timeout_round_trip(self):
        from openagentmesh._errors import from_envelope

        err = from_envelope({
            "code": "timeout",
            "message": "No message on x within 30.0s",
            "agent": "",
            "request_id": "",
            "details": {},
        })
        assert isinstance(err, MeshTimeout)

    def test_invocation_mismatch_round_trip(self):
        from openagentmesh._errors import from_envelope

        err = from_envelope({
            "code": "invocation_mismatch",
            "message": "wrong verb",
            "agent": "x",
            "request_id": "",
            "details": {},
        })
        assert isinstance(err, InvocationMismatch)

    def test_unknown_code_falls_back_to_base(self):
        """Forward-compatibility: unknown codes deserialize to MeshError, not raise."""
        from openagentmesh._errors import from_envelope

        err = from_envelope({
            "code": "future_code",
            "message": "from a newer SDK",
            "agent": "",
            "request_id": "",
            "details": {},
        })
        assert isinstance(err, MeshError)
        assert err.code == "future_code"
        # Should NOT be a known subclass
        assert type(err) is MeshError


# --- End-to-end: validation vs handler distinction (uses embedded NATS) ---


class TestValidationVsHandlerDistinction:
    async def test_malformed_payload_raises_invalid_input(self):
        """Caller sends payload that fails pydantic schema → InvalidInput, not HandlerError."""
        spec = AgentSpec(name="strict-scorer", description="Scorer requiring `text` field")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def strict(req: _Input) -> _Output:
                return _Output(result=req.text.upper())

            with pytest.raises(InvalidInput) as exc_info:
                await mesh.call("strict-scorer", {"wrong_field": "x"})

            err = exc_info.value
            assert err.code == "invalid_input"
            assert err.agent == "strict-scorer"
            # Pydantic-style error structure inside details
            assert "errors" in err.details
            assert isinstance(err.details["errors"], list)
            assert len(err.details["errors"]) >= 1

    async def test_handler_exception_raises_handler_error(self):
        """Handler runs and raises a non-MeshError → HandlerError."""
        spec = AgentSpec(name="boom", description="Always raises")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def handler(req: _Input) -> _Output:
                raise RuntimeError("handler crash")

            with pytest.raises(HandlerError) as exc_info:
                await mesh.call("boom", {"text": "hello"})

            err = exc_info.value
            assert err.code == "handler_error"
            assert "handler crash" in err.message

    async def test_handler_meshError_subclass_propagates(self):
        """If handler raises a MeshError subclass directly, it must NOT be wrapped as HandlerError."""
        spec = AgentSpec(name="picky", description="Raises a domain-specific MeshError")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def handler(req: _Input) -> _Output:
                raise InvalidInput(
                    agent="picky",
                    message="custom rejection",
                    details={"errors": [{"loc": ["text"], "msg": "too short", "type": "custom"}]},
                )

            with pytest.raises(InvalidInput) as exc_info:
                await mesh.call("picky", {"text": "x"})

            err = exc_info.value
            assert err.code == "invalid_input"
            assert "custom rejection" in err.message

    async def test_distinct_codes_on_wire(self):
        """Validation and handler errors must surface with different codes on the error topic."""
        import json

        spec_v = AgentSpec(name="needs-text", description="Validates input")
        spec_h = AgentSpec(name="crashes", description="Handler crashes")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec_v)
            async def v(req: _Input) -> _Output:
                return _Output(result=req.text)

            @mesh.agent(spec_h)
            async def h(req: _Input) -> _Output:
                raise ValueError("oops")

            v_errors: list[dict] = []
            h_errors: list[dict] = []

            async def cb_v(msg):
                v_errors.append(json.loads(msg.data))

            async def cb_h(msg):
                h_errors.append(json.loads(msg.data))

            await mesh._nc.subscribe("mesh.errors.needs-text", cb=cb_v)
            await mesh._nc.subscribe("mesh.errors.crashes", cb=cb_h)

            with pytest.raises(InvalidInput):
                await mesh.call("needs-text", {"wrong": "shape"})
            with pytest.raises(HandlerError):
                await mesh.call("crashes", {"text": "ok"})

            await asyncio.sleep(0.1)

            assert len(v_errors) == 1
            assert v_errors[0]["code"] == "invalid_input"

            assert len(h_errors) == 1
            assert h_errors[0]["code"] == "handler_error"


# --- NotFound surfaces from discovery ---


class TestNotFoundFromDiscovery:
    async def test_contract_missing_raises_not_found(self):
        async with AgentMesh.local() as mesh:
            with pytest.raises(NotFound) as exc_info:
                await mesh.contract("does-not-exist")

            err = exc_info.value
            assert err.code == "not_found"
            assert err.agent == "does-not-exist"

    async def test_not_found_caught_as_mesh_error_too(self):
        """Backwards-compat: existing `except MeshError` still catches the new subclass."""
        async with AgentMesh.local() as mesh:
            with pytest.raises(MeshError):
                await mesh.contract("does-not-exist")


# --- Drift fix: MeshTimeout used everywhere, no raw MeshError(code='timeout') ---


class TestMeshTimeoutSubclassUsedConsistently:
    def test_no_raw_meshError_timeout_in_source(self):
        """Source must not raise `MeshError(code='timeout', ...)` directly — use MeshTimeout."""
        import pathlib

        src = pathlib.Path(__file__).resolve().parent.parent / "src" / "openagentmesh"
        offenders = []
        for py in src.rglob("*.py"):
            text = py.read_text()
            # naive but effective: any line raising MeshError with a timeout code literal
            for lineno, line in enumerate(text.splitlines(), start=1):
                if 'code="timeout"' in line and "MeshError(" in line:
                    offenders.append(f"{py}:{lineno}")
                if "code='timeout'" in line and "MeshError(" in line:
                    offenders.append(f"{py}:{lineno}")
        assert not offenders, (
            "Use MeshTimeout(...) instead of MeshError(code='timeout', ...). "
            "Offenders:\n  " + "\n  ".join(offenders)
        )

    def test_no_raw_meshError_not_found_in_source(self):
        """Source must not raise `MeshError(code='not_found', ...)` directly — use NotFound."""
        import pathlib

        src = pathlib.Path(__file__).resolve().parent.parent / "src" / "openagentmesh"
        offenders = []
        for py in src.rglob("*.py"):
            text = py.read_text()
            for lineno, line in enumerate(text.splitlines(), start=1):
                if 'code="not_found"' in line and "MeshError(" in line:
                    offenders.append(f"{py}:{lineno}")
                if "code='not_found'" in line and "MeshError(" in line:
                    offenders.append(f"{py}:{lineno}")
        assert not offenders, (
            "Use NotFound(...) instead of MeshError(code='not_found', ...). "
            "Offenders:\n  " + "\n  ".join(offenders)
        )

    def test_no_raw_meshError_connection_failed_in_source(self):
        """Source must not raise `MeshError(code='connection_failed', ...)` directly — use ConnectionFailed."""
        import pathlib

        src = pathlib.Path(__file__).resolve().parent.parent / "src" / "openagentmesh"
        offenders = []
        for py in src.rglob("*.py"):
            text = py.read_text()
            for lineno, line in enumerate(text.splitlines(), start=1):
                if 'code="connection_failed"' in line and "MeshError(" in line:
                    offenders.append(f"{py}:{lineno}")
                if "code='connection_failed'" in line and "MeshError(" in line:
                    offenders.append(f"{py}:{lineno}")
        assert not offenders, (
            "Use ConnectionFailed(...) instead of MeshError(code='connection_failed', ...). "
            "Offenders:\n  " + "\n  ".join(offenders)
        )
