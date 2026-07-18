"""Mesh error taxonomy (ADR-0057).

Single home for `MeshError` and every categorical subclass. Each subclass
declares its wire `code` as a class-level default; the base constructor reads it
and instances may carry an overriding code (e.g. errors decoded off the wire).

Wire-side reconstruction (`from_envelope`) maps codes back to the matching
subclass so a remote agent's `InvalidInput` is caught locally as
`except InvalidInput`, not just as `except MeshError`.
"""

from __future__ import annotations

import json
from typing import Any


class MeshError(Exception):
    """Structured error from the mesh (local or remote).

    Carries the wire envelope shape defined in ADR-0001:
    `code`, `message`, `agent`, `request_id`, `details`.
    """

    code: str = "mesh_error"

    def __init__(
        self,
        *,
        message: str = "",
        agent: str = "",
        request_id: str = "",
        details: dict[str, Any] | None = None,
        code: str | None = None,
    ):
        super().__init__(message)
        self.code = code or self.__class__.code
        self.message = message
        self.agent = agent
        self.request_id = request_id
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "agent": self.agent,
            "request_id": self.request_id,
            "details": self.details,
        }

    def to_json(self) -> bytes:
        return json.dumps(self.to_dict()).encode()


class InvalidInput(MeshError):
    """Caller's input failed schema validation."""

    code: str = "invalid_input"

    def __init__(
        self,
        *,
        agent: str = "",
        request_id: str = "",
        message: str = "Input validation failed",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            agent=agent,
            request_id=request_id,
            details=details,
        )


class HandlerError(MeshError):
    """Uncategorized exception raised inside the agent handler body."""

    code: str = "handler_error"


class InvocationMismatch(MeshError):
    """Verb/shape mismatch between the call and the agent's capabilities (ADR-0047)."""

    code: str = "invocation_mismatch"

    def __init__(self, *, agent: str = "", message: str = "", request_id: str = ""):
        super().__init__(
            message=message or f"Invocation mismatch for agent '{agent}'",
            agent=agent,
            request_id=request_id,
        )


class NotFound(MeshError):
    """Agent missing from registry/catalog."""

    code: str = "not_found"

    def __init__(self, *, agent: str, request_id: str = ""):
        super().__init__(
            message=f"Agent '{agent}' not found",
            agent=agent,
            request_id=request_id,
        )


class NotAvailable(MeshError):
    """Agent registered in the catalog but currently offline (ADR-0055).

    Raised when a request gets no responders while the agent is still
    listed in the catalog: a lifecycle gate has taken it offline (or it is
    draining). The agent exists; retry when its condition changes. Distinct
    from `NotFound` (not registered) and `InvocationMismatch` (no RPC
    surface).
    """

    code: str = "not_available"

    def __init__(self, *, agent: str, request_id: str = ""):
        super().__init__(
            message=f"Agent '{agent}' is registered but currently offline (lifecycle gate)",
            agent=agent,
            request_id=request_id,
        )


class ConnectionFailed(MeshError):
    """Initial NATS connect or reconnect failed."""

    code: str = "connection_failed"


class ConnectionDenied(MeshError):
    """The NATS server rejected the connection or a subject operation (ADR-0038).

    Raised when the server requires credentials the client did not present,
    the presented credentials are invalid, or a publish/subscribe hits a
    permission the connection's identity lacks.
    """

    code: str = "connection_denied"


class AgentDied(MeshError):
    """The target agent left the mesh during an in-flight request (ADR-0040).

    Raised when a death notice for the target arrives before its reply:
    sub-second failure instead of waiting out the timeout. `details` carries
    the death notice payload (reason, detected_at, instance_id).
    """

    code: str = "agent_died"


class KVKeyExists(MeshError):
    """A KV ``create()`` call collided with an existing key (ADR-0060)."""

    code: str = "kv_key_exists"

    def __init__(self, *, key: str = "", message: str = ""):
        super().__init__(
            message=message or f"KV key already exists: {key!r}",
            details={"key": key},
        )
        self.key = key


class MeshTimeout(MeshError):
    """No reply within the deadline (ADR-0034)."""

    code: str = "timeout"

    def __init__(self, subject: str, timeout: float):
        super().__init__(
            message=f"No message on {subject} within {timeout}s",
        )
        self.subject = subject
        self.timeout = timeout


class ChunkSequenceError(MeshError):
    """Stream chunks arrived out of order (ADR-0005, defensive)."""

    code: str = "chunk_sequence_error"

    def __init__(
        self,
        *,
        agent: str = "",
        request_id: str = "",
        details: dict[str, Any] | None = None,
    ):
        details = details or {}
        super().__init__(
            message=(
                f"Expected chunk seq {details.get('expected_seq', '?')}, "
                f"got {details.get('got_seq', '?')}"
            ),
            agent=agent,
            request_id=request_id,
            details=details,
        )


_CODE_TO_CLASS: dict[str, type[MeshError]] = {
    cls.code: cls
    for cls in (
        InvalidInput,
        HandlerError,
        InvocationMismatch,
        NotFound,
        NotAvailable,
        ConnectionFailed,
        ConnectionDenied,
        AgentDied,
        KVKeyExists,
        MeshTimeout,
        ChunkSequenceError,
    )
}


def from_envelope(payload: dict[str, Any]) -> MeshError:
    """Reconstruct the matching `MeshError` subclass from a wire envelope.

    Unknown codes deserialize to a plain `MeshError` carrying the wire code,
    so newer SDK versions producing codes this version doesn't recognize
    don't raise during deserialization.
    """
    code = payload.get("code", "mesh_error")
    klass = _CODE_TO_CLASS.get(code)
    message = payload.get("message", "")
    agent = payload.get("agent", "")
    request_id = payload.get("request_id", "")
    details = payload.get("details") or {}

    if klass is None:
        return MeshError(
            message=message,
            agent=agent,
            request_id=request_id,
            details=details,
            code=code,
        )

    if klass is MeshTimeout:
        # Constructor signature differs — synthesize the subject/timeout from message
        subject = details.get("subject", "")
        timeout = float(details.get("timeout", 0.0))
        err = MeshTimeout(subject=subject, timeout=timeout)
        err.message = message or err.message
        err.agent = agent
        err.request_id = request_id
        return err

    if klass is NotFound:
        return NotFound(agent=agent, request_id=request_id)

    if klass is NotAvailable:
        return NotAvailable(agent=agent, request_id=request_id)

    if klass is InvocationMismatch:
        return InvocationMismatch(agent=agent, message=message, request_id=request_id)

    if klass is ChunkSequenceError:
        return ChunkSequenceError(agent=agent, request_id=request_id, details=details)

    return klass(
        message=message,
        agent=agent,
        request_id=request_id,
        details=details,
    )
