"""OpenAgentMesh: protocol and SDK for multi-agent interaction."""

from ._mesh import AgentMesh
from ._models import (
    AgentContract,
    AgentSpec,
    StreamingRequired,
    CatalogEntry,
    ChunkSequenceError,
    MeshError,
    MeshTimeout,
    StreamingNotSupported,
)

__all__ = [
    "AgentMesh",
    "AgentSpec",
    "AgentContract",
    "StreamingRequired",
    "CatalogEntry",
    "ChunkSequenceError",
    "MeshError",
    "MeshTimeout",
    "StreamingNotSupported",
]
