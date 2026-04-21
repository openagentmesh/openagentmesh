"""Data models for OpenAgentMesh."""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any, Literal

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

    def to_tool_schema(self) -> dict[str, Any]:
        """Provider-neutral tool triple: name + description + input_schema."""
        self._assert_invocable()
        return {
            "name": _sanitize_name(self.name),
            "description": _build_description(self.description, self.output_schema),
            "input_schema": self.input_schema or {"type": "object", "properties": {}},
        }

    def to_openai_tool(
        self,
        *,
        api: Literal["chat", "responses"] = "chat",
        strict: bool = False,
    ) -> dict[str, Any]:
        """OpenAI-format tool definition (Chat Completions or Responses API)."""
        base = self.to_tool_schema()
        schema = copy.deepcopy(base["input_schema"])
        if strict:
            schema = _strict_clean_schema(schema)

        if api == "chat":
            fn: dict[str, Any] = {
                "name": base["name"],
                "description": base["description"],
                "parameters": schema,
            }
            if strict:
                fn["strict"] = True
            return {"type": "function", "function": fn}

        result: dict[str, Any] = {
            "type": "function",
            "name": base["name"],
            "description": base["description"],
            "parameters": schema,
        }
        if strict:
            result["strict"] = True
        return result

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Anthropic Messages API tool definition."""
        return self.to_tool_schema()

    def _assert_invocable(self) -> None:
        if not self.invocable:
            raise ValueError(f"Agent '{self.name}' is not invocable (publisher)")

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


_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_STRICT_STRIP = frozenset({
    "format", "pattern", "minLength", "maxLength",
    "minimum", "maximum", "minItems", "maxItems",
    "default", "title",
})


def _sanitize_name(name: str) -> str:
    sanitized = name.replace(".", "_")
    if not _NAME_RE.match(sanitized):
        raise ValueError(
            f"Tool name '{sanitized}' (from '{name}') does not match "
            f"{_NAME_RE.pattern}"
        )
    return sanitized


def _build_description(description: str, output_schema: dict[str, Any] | None) -> str:
    if not output_schema:
        return description
    props = output_schema.get("properties", {})
    if not props:
        return description
    fields = ", ".join(props.keys())
    return f"{description}\nReturns: {fields}."


def _strict_clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    schema = copy.deepcopy(schema)
    return _strict_clean_node(schema)


def _strict_clean_node(node: dict[str, Any]) -> dict[str, Any]:
    for kw in _STRICT_STRIP:
        node.pop(kw, None)

    if node.get("type") == "object":
        node["additionalProperties"] = False
        props = node.get("properties", {})
        required = set(node.get("required", []))
        for prop_name, prop_schema in props.items():
            _strict_clean_node(prop_schema)
            if prop_name not in required:
                current_type = prop_schema.get("type")
                if current_type and current_type != "null":
                    prop_schema["type"] = [current_type, "null"]
        node["required"] = sorted(props.keys())

    if node.get("type") == "array":
        items = node.get("items")
        if isinstance(items, dict):
            _strict_clean_node(items)

    return node


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
        self.message = message
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


class InvocationMismatch(MeshError):
    """Raised when the invocation verb doesn't match the agent's capabilities (ADR-0047)."""

    def __init__(self, agent: str = "", message: str = "", request_id: str = ""):
        super().__init__(
            code="invocation_mismatch",
            message=message or f"Invocation mismatch for agent '{agent}'",
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
