"""OpenAgentMesh: protocol and SDK for multi-agent interaction."""

from ._errors import (
    ChunkSequenceError,
    ConnectionFailed,
    HandlerError,
    InvalidInput,
    InvocationMismatch,
    MeshError,
    MeshTimeout,
    NotFound,
)
from ._mesh import AgentMesh
from ._models import (
    AgentContract,
    AgentSpec,
    CatalogEntry,
)

__all__ = [
    "AgentMesh",
    "AgentContract",
    "AgentSpec",
    "CatalogEntry",
    "ChunkSequenceError",
    "ConnectionFailed",
    "HandlerError",
    "InvalidInput",
    "InvocationMismatch",
    "MeshError",
    "MeshTimeout",
    "NotFound",
]
