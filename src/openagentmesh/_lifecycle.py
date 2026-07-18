"""Agent lifecycle gates (ADR-0055).

A condition gates whether an agent is subscribed at all. The SDK evaluates
the condition's signal and brings the agent online (subscribes its RPC
subject, binds its sources) or offline (drains in-flight handlers, then
unsubscribes) as the predicate flips. Conditions are runtime wiring, not
catalog material: a gated agent stays in the catalog while offline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Condition(Protocol):
    """A lifecycle gate for an agent (ADR-0055).

    The SDK re-evaluates the predicate whenever the underlying signal
    changes. True brings the agent online; False drains in-flight handlers
    and takes it offline. The signal source (KV key, NATS subject, ...) is
    the concrete implementation's concern.
    """

    predicate: Callable[[Any], bool]
    initial: bool
    drain_timeout: float


@dataclass(frozen=True)
class KVCondition:
    """Gate on a key in the ``mesh-context`` KV bucket.

    Returned by :meth:`AgentMesh.kv_condition`. The predicate receives the
    key's raw ``bytes`` value, or ``None`` when the key is absent or
    deleted. On mesh entry the current value is read and applied
    immediately; ``initial`` is only the fallback when that read fails.
    """

    key: str
    predicate: Callable[[bytes | None], bool]
    initial: bool = False
    drain_timeout: float = 30.0


@dataclass(frozen=True)
class SubjectCondition:
    """Gate on messages arriving on a plain NATS subject.

    Returned by :meth:`AgentMesh.subject_condition`. The predicate receives
    each message's payload ``bytes``; the agent's state follows the most
    recent verdict. ``initial`` is the state before the first message.
    """

    subject: str
    predicate: Callable[[bytes], bool]
    initial: bool = False
    drain_timeout: float = 30.0
