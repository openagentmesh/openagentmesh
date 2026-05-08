"""Agent sources: declarative trigger surfaces (ADR-0052).

A source binds an agent handler to a NATS subject or a KV namespace pattern.
Sources are runtime wiring, not part of the agent's catalog contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class SubjectSource:
    """A source binding to a NATS subject (or wildcard).

    Returned by :meth:`AgentMesh.subject_source`.
    """

    subject: str
    queue_group: str | None = None


@dataclass(frozen=True)
class KVSource:
    """A source binding to a KV pattern in the ``mesh-context`` bucket.

    Returned by :meth:`AgentMesh.kv_source`.
    """

    pattern: str
    queue_group: str | None = None
    on_init: Literal["replay", "skip"] = "replay"


@dataclass
class MeshMessage(Generic[T]):
    """Full NATS envelope passed to handlers that accept it via type hint.

    The handler's annotation drives delivery shape: ``bytes`` → raw bytes,
    ``Model`` (Pydantic) → validated payload, ``MeshMessage[Model]`` → full
    envelope including subject, headers, and validated payload.
    """

    subject: str
    headers: dict[str, str] = field(default_factory=dict)
    payload: T | None = None
