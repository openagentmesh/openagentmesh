"""Unit tests for MeshError."""

from agentmesh.errors import MeshError


def test_constructor_sets_all_fields():
    err = MeshError(
        code="timeout",
        message="Agent timed out",
        agent="summarizer",
        request_id="req-123",
        details={"elapsed_ms": 30000},
    )
    assert err.code == "timeout"
    assert err.message == "Agent timed out"
    assert err.agent == "summarizer"
    assert err.request_id == "req-123"
    assert err.details == {"elapsed_ms": 30000}


def test_constructor_defaults():
    err = MeshError(code="not_found", message="Missing agent")
    assert err.agent == ""
    assert err.request_id == ""
    assert err.details == {}


def test_str_format():
    err = MeshError(code="handler_error", message="boom")
    assert str(err) == "handler_error: boom"


def test_to_dict_returns_all_fields():
    err = MeshError(
        code="validation_error",
        message="Invalid input",
        agent="greeter",
        request_id="abc",
        details={"field": "name"},
    )
    d = err.to_dict()
    assert d == {
        "code": "validation_error",
        "message": "Invalid input",
        "agent": "greeter",
        "request_id": "abc",
        "details": {"field": "name"},
    }


def test_to_dict_defaults():
    err = MeshError(code="not_found", message="x")
    d = err.to_dict()
    assert d["agent"] == ""
    assert d["request_id"] == ""
    assert d["details"] == {}


def test_is_exception():
    err = MeshError(code="rate_limited", message="too fast")
    assert isinstance(err, Exception)
