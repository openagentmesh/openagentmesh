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
    NotAvailable,
    NotFound,
)
from ._lifecycle import Condition, KVCondition, SubjectCondition
from ._mesh import AgentMesh
from ._models import (
    AgentContract,
    AgentSpec,
    CatalogEntry,
    DeathNotice,
    LogEvent,
    ObserveConfig,
)
from ._sources import KVSource, MeshMessage, SubjectSource
from ._usage import Usage, report_usage

__all__ = [
    "AgentDied",
    "AgentMesh",
    "AgentContract",
    "AgentSpec",
    "CatalogEntry",
    "ChunkSequenceError",
    "Condition",
    "ConnectionDenied",
    "ConnectionFailed",
    "DeathNotice",
    "HandlerError",
    "InvalidInput",
    "InvocationMismatch",
    "KVCondition",
    "KVEntry",
    "KVKeyExists",
    "KVSource",
    "LogEvent",
    "MeshError",
    "MeshMessage",
    "MeshTimeout",
    "NotAvailable",
    "NotFound",
    "SubjectCondition",
    "ObserveConfig",
    "SubjectSource",
    "Usage",
    "report_usage",
]
