"""OpenAgentMesh: protocol and SDK for multi-agent interaction."""

from ._mesh import AgentMesh
from ._models import (
    AgentContract,
    AgentSpec,
    BufferedNotSupported,
    CatalogEntry,
    ChunkSequenceError,
    MeshError,
    StreamingNotSupported,
)

__all__ = [
    "AgentMesh",
    "AgentSpec",
    "AgentContract",
    "BufferedNotSupported",
    "CatalogEntry",
    "ChunkSequenceError",
    "MeshError",
    "StreamingNotSupported",
]
