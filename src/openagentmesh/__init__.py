"""OpenAgentMesh: protocol and SDK for multi-agent interaction."""

from ._context import KVEntry
from ._errors import (
    AgentDied,
    ChunkSequenceError,
    ConnectionDenied,
    ConnectionFailed,
    HandlerError,
    InvalidInput,
    InvocationMismatch,
    KVKeyExists,
    MeshError,
    MeshTimeout,
    NotFound,
)
from ._mesh import AgentMesh
from ._models import (
    AgentContract,
    AgentSpec,
    CatalogEntry,
    DeathNotice,
)
from ._sources import KVSource, MeshMessage, SubjectSource

__all__ = [
    "AgentDied",
    "AgentMesh",
    "AgentContract",
    "AgentSpec",
    "CatalogEntry",
    "ChunkSequenceError",
    "ConnectionDenied",
    "ConnectionFailed",
    "DeathNotice",
    "HandlerError",
    "InvalidInput",
    "InvocationMismatch",
    "KVEntry",
    "KVKeyExists",
    "KVSource",
    "MeshError",
    "MeshMessage",
    "MeshTimeout",
    "NotFound",
    "SubjectSource",
]
