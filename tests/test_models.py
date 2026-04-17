"""Tests for AgentSpec, CatalogEntry, and handler inspection (ADRs 0028, 0030, 0031)."""

import pytest
from pydantic import BaseModel

from openagentmesh import AgentSpec, CatalogEntry, MeshError, MeshTimeout
from openagentmesh._models import (
    BufferedNotSupported,
    ChunkSequenceError,
    StreamingNotSupported,
)
from openagentmesh._handler import inspect_handler


# --- Test fixtures ---


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    reply: str


class Chunk(BaseModel):
    delta: str


class Event(BaseModel):
    data: str


# --- AgentSpec (ADR-0030) ---


class TestAgentSpec:
    def test_minimal(self):
        spec = AgentSpec(name="echo", description="Echoes messages")
        assert spec.name == "echo"
        assert spec.description == "Echoes messages"
        assert spec.channel is None
        assert spec.tags == []
        assert spec.version == "0.1.0"

    def test_full(self):
        spec = AgentSpec(
            name="classifier",
            channel="nlp",
            description="Classifies text sentiment",
            tags=["nlp", "classification"],
            version="1.0.0",
        )
        assert spec.channel == "nlp"
        assert spec.tags == ["nlp", "classification"]
        assert spec.version == "1.0.0"

    def test_no_type_field(self):
        """ADR-0031: AgentSpec has no type field."""
        spec = AgentSpec(name="x", description="x")
        assert not hasattr(spec, "type")


# --- CatalogEntry (ADR-0028) ---


class TestCatalogEntry:
    def test_attribute_access(self):
        """ADR-0028: entry.name not entry['name']."""
        entry = CatalogEntry(name="echo", description="Echoes messages")
        assert entry.name == "echo"
        assert entry.description == "Echoes messages"

    def test_defaults(self):
        entry = CatalogEntry(name="x", description="x")
        assert entry.invocable is True
        assert entry.streaming is False
        assert entry.version == "0.1.0"
        assert entry.tags == []
        assert entry.channel is None

    def test_capability_booleans(self):
        """ADR-0031: invocable and streaming replace type taxonomy."""
        entry = CatalogEntry(
            name="summarizer", description="Streams summaries",
            invocable=True, streaming=True,
        )
        assert entry.invocable is True
        assert entry.streaming is True


# --- Handler inspection (ADR-0031) ---


class TestHandlerInspection:
    def test_buffered_handler(self):
        """Buffered: invocable=True, streaming=False."""

        async def handler(req: EchoInput) -> EchoOutput:
            return EchoOutput(reply=req.message)

        info = inspect_handler(handler)
        assert info.invocable is True
        assert info.streaming is False
        assert info.input_model is EchoInput
        assert info.output_model is EchoOutput

    def test_streaming_handler(self):
        """Streaming: invocable=True, streaming=True."""

        async def handler(req: EchoInput) -> Chunk:
            yield Chunk(delta="hello")

        info = inspect_handler(handler)
        assert info.invocable is True
        assert info.streaming is True
        assert info.input_model is EchoInput
        assert info.output_model is Chunk

    def test_event_emitter(self):
        """Event emitter: invocable=False, streaming=True."""

        async def handler() -> Event:
            yield Event(data="tick")

        info = inspect_handler(handler)
        assert info.invocable is False
        assert info.streaming is True
        assert info.output_model is Event

    def test_sync_handler_rejected(self):
        def handler(req: EchoInput) -> EchoOutput:
            return EchoOutput(reply=req.message)

        with pytest.raises(TypeError, match="must be async"):
            inspect_handler(handler)

    def test_no_input_no_yield_rejected(self):
        """No input param + no yield = invalid (fourth combination)."""

        async def handler() -> EchoOutput:
            return EchoOutput(reply="nope")

        with pytest.raises(TypeError, match="invocable or streaming"):
            inspect_handler(handler)


# --- Error subclasses (ADR-0005) ---


class TestErrorSubclasses:
    def test_streaming_not_supported_is_mesh_error(self):
        err = StreamingNotSupported(agent="echo")
        assert isinstance(err, MeshError)
        assert err.code == "streaming_not_supported"
        assert "echo" in str(err)

    def test_buffered_not_supported_is_mesh_error(self):
        err = BufferedNotSupported(agent="streamer")
        assert isinstance(err, MeshError)
        assert err.code == "buffered_not_supported"
        assert "streamer" in str(err)

    def test_chunk_sequence_error_is_mesh_error(self):
        err = ChunkSequenceError(
            agent="streamer",
            details={"expected_seq": 3, "got_seq": 5},
        )
        assert isinstance(err, MeshError)
        assert err.code == "chunk_sequence_error"
        assert err.details["expected_seq"] == 3
        assert err.details["got_seq"] == 5

    def test_catch_specific_subclass(self):
        """Callers can except StreamingNotSupported without catching all MeshErrors."""
        try:
            raise StreamingNotSupported(agent="echo")
        except StreamingNotSupported:
            pass  # caught by subclass

        with pytest.raises(StreamingNotSupported):
            raise StreamingNotSupported(agent="echo")


class TestMeshTimeout:
    def test_inherits_mesh_error(self):
        err = MeshTimeout(subject="mesh.results.abc", timeout=30.0)
        assert isinstance(err, MeshError)

    def test_code_is_timeout(self):
        err = MeshTimeout(subject="mesh.results.abc", timeout=30.0)
        assert err.code == "timeout"

    def test_message_includes_subject_and_timeout(self):
        err = MeshTimeout(subject="mesh.results.abc", timeout=30.0)
        assert "mesh.results.abc" in str(err)
        assert "30.0" in str(err)

    def test_to_dict(self):
        err = MeshTimeout(subject="mesh.results.abc", timeout=30.0)
        d = err.to_dict()
        assert d["code"] == "timeout"
