"""Data models for OpenAgentMesh."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class AgentSpec(BaseModel):
    """Agent registration metadata. Passed to ``@mesh.agent(spec)``.

    Declares *what* the agent is. Capabilities (``invocable``, ``streaming``)
    are inferred from the handler shape at registration time (ADR-0031).
    """

    name: str
    description: str
    channel: str | None = None
    tags: list[str] = Field(default_factory=list)
    version: str = "0.1.0"


class CatalogEntry(BaseModel):
    """Lightweight catalog entry returned by ``mesh.catalog()`` (ADR-0028)."""

    name: str
    description: str
    channel: str | None = None
    version: str = "0.1.0"
    tags: list[str] = Field(default_factory=list)
    invocable: bool = True
    streaming: bool = False


class AgentContract(BaseModel):
    """Full agent contract stored in ``mesh-registry`` KV.

    Superset of A2A Agent Card. OAM-specific fields live under
    the ``x-agentmesh`` namespace when serialized to JSON, but are
    flat attributes on this model for ergonomics.
    """

    # A2A Agent Card top-level fields
    name: str
    description: str
    version: str = "0.1.0"
    capabilities: dict[str, Any] = Field(default_factory=dict)
    skills: list[dict[str, Any]] = Field(default_factory=list)

    # OAM fields (x-agentmesh namespace when serialized)
    channel: str | None = None
    subject: str = ""
    tags: list[str] = Field(default_factory=list)
    invocable: bool = True
    streaming: bool = False
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    chunk_schema: dict[str, Any] | None = None
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_catalog_entry(self) -> CatalogEntry:
        """Project to a lightweight catalog entry."""
        return CatalogEntry(
            name=self.name,
            description=self.description,
            channel=self.channel,
            version=self.version,
            tags=self.tags,
            invocable=self.invocable,
            streaming=self.streaming,
        )

    def to_registry_json(self) -> str:
        """Serialize to the registry JSON format (A2A-compatible with x-agentmesh)."""
        skill = {
            "id": self.name,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
        }
        if self.input_schema:
            skill["inputSchema"] = self.input_schema
        if self.output_schema:
            skill["outputSchema"] = self.output_schema

        doc: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": {
                "streaming": self.streaming,
                "invocable": self.invocable,
            },
            "skills": [skill],
            "x-agentmesh": {
                "channel": self.channel,
                "subject": self.subject,
                "tags": self.tags,
                "registered_at": self.registered_at.isoformat(),
            },
        }
        if self.chunk_schema:
            doc["x-agentmesh"]["chunk_schema"] = self.chunk_schema

        import json

        return json.dumps(doc)


class MeshError(Exception):
    """Structured error from the mesh (local or remote)."""

    def __init__(
        self,
        code: str,
        message: str,
        agent: str = "",
        request_id: str = "",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.agent = agent
        self.request_id = request_id
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "agent": self.agent,
            "request_id": self.request_id,
            "details": self.details,
        }

    def to_json(self) -> bytes:
        import json

        return json.dumps(self.to_dict()).encode()


class StreamingNotSupported(MeshError):
    """Raised when ``mesh.stream()`` targets a buffered agent (ADR-0005)."""

    def __init__(self, agent: str = "", request_id: str = ""):
        super().__init__(
            code="streaming_not_supported",
            message=f"Agent '{agent}' does not support streaming",
            agent=agent,
            request_id=request_id,
        )


class BufferedNotSupported(MeshError):
    """Raised when ``mesh.call()`` targets a streaming-only agent (ADR-0005)."""

    def __init__(self, agent: str = "", request_id: str = ""):
        super().__init__(
            code="buffered_not_supported",
            message=f"Agent '{agent}' is streaming-only; use mesh.stream() instead",
            agent=agent,
            request_id=request_id,
        )


class ChunkSequenceError(MeshError):
    """Raised when stream chunks arrive out of order (ADR-0005)."""

    def __init__(
        self,
        agent: str = "",
        request_id: str = "",
        details: dict[str, Any] | None = None,
    ):
        details = details or {}
        super().__init__(
            code="chunk_sequence_error",
            message=(
                f"Expected chunk seq {details.get('expected_seq', '?')}, "
                f"got {details.get('got_seq', '?')}"
            ),
            agent=agent,
            request_id=request_id,
            details=details,
        )


class MeshTimeout(MeshError):
    """Raised when no message arrives within the timeout window (ADR-0034)."""

    def __init__(self, subject: str, timeout: float):
        super().__init__(
            code="timeout",
            message=f"No message on {subject} within {timeout}s",
        )
        self.subject = subject
        self.timeout = timeout
