"""Data models for OpenAgentMesh."""

from __future__ import annotations

import copy
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_NAME_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_agent_name(value: str) -> str:
    if not value:
        raise ValueError("agent name must not be empty")
    if value.startswith(".") or value.endswith("."):
        raise ValueError(f"agent name '{value}' must not start or end with '.'")
    if ".." in value:
        raise ValueError(f"agent name '{value}' must not contain consecutive dots")
    for seg in value.split("."):
        if not _NAME_SEGMENT_RE.match(seg):
            raise ValueError(
                f"agent name '{value}' has invalid segment '{seg}' "
                f"(allowed: {_NAME_SEGMENT_RE.pattern})"
            )
    return value


class AgentSpec(BaseModel):
    """Agent registration metadata. Passed to ``@mesh.agent(spec)``.

    Declares *what* the agent is. Capabilities (``invocable``, ``streaming``)
    are inferred from the handler shape at registration time (ADR-0031).

    ``name`` is a dotted identifier, e.g. ``"finance.risk.scorer"`` or
    ``"echo"`` (ADR-0049). The full name maps to the NATS subject tail
    after ``mesh.agent.``.
    """

    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    version: str = "0.1.0"

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        return _validate_agent_name(v)


class CatalogEntry(BaseModel):
    """Lightweight catalog entry returned by ``mesh.catalog()`` (ADR-0028)."""

    name: str
    description: str
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
    subject: str = ""
    tags: list[str] = Field(default_factory=list)
    invocable: bool = True
    streaming: bool = False
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    chunk_schema: dict[str, Any] | None = None
    mcp: bool | None = None  # MCP export opt-in/out (ADR-0003); None = mesh default
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

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
            version=self.version,
            tags=self.tags,
            invocable=self.invocable,
            streaming=self.streaming,
        )

    def to_registry_json(self) -> str:
        """Serialize to the registry JSON format (A2A-compatible with x-agentmesh)."""
        skill: dict[str, Any] = {
            "id": self.name,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
        }
        if self.input_schema:
            skill["inputSchema"] = self.input_schema
        if self.output_schema:
            skill["outputSchema"] = self.output_schema

        xam: dict[str, Any] = {
            "subject": self.subject,
            "tags": self.tags,
            "registered_at": self.registered_at.isoformat(),
        }
        if self.chunk_schema:
            xam["chunk_schema"] = self.chunk_schema
        if self.mcp is not None:
            xam["mcp"] = self.mcp

        doc: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": {
                "streaming": self.streaming,
                "invocable": self.invocable,
            },
            "skills": [skill],
            "x-agentmesh": xam,
        }

        import json

        return json.dumps(doc)

    def to_agent_card(self, url: str | None = None) -> dict[str, Any]:
        """A2A Agent Card projection (ADR-0012).

        Thin by design: the registry document minus the ``x-agentmesh``
        extension block, with ``url`` injected when the caller (typically a
        federation gateway) provides one. Agents have no HTTP URL inside the
        mesh, so none is stored.
        """
        import json

        card: dict[str, Any] = json.loads(self.to_registry_json())
        card.pop("x-agentmesh", None)
        if url is not None:
            card["url"] = url
        return card


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


# Error classes moved to ._errors per ADR-0057.
