# ADR-0057: Error taxonomy and dedicated `_errors` module

- **Type:** api-design / structure
- **Date:** 2026-05-07
- **Status:** implemented
- **Amends:** ADR-0001 (error envelope), ADR-0005 (streaming codes), ADR-0034 (`MeshTimeout`), ADR-0044 (responder/streamer rename), ADR-0047 (`InvocationMismatch`)
- **Source:** v1.0 milestone audit — original REQ TRAN-05 (`validation_error` code) never lifted into an ADR; review surfaced broader scattering of error classes inside `_models.py` and inconsistent code-vs-class usage

## Context

Error classes have accumulated across several ADRs without a unifying decision on where they live or how new categorical errors enter the system.

Today:

- `MeshError`, `InvocationMismatch`, `ChunkSequenceError`, `MeshTimeout` all live in `_models.py` next to `AgentSpec`, `AgentContract`, `CatalogEntry`. The file is a mix of structural Pydantic models and exception types.
- Some codes are raised through a dedicated subclass (`invocation_mismatch`, `chunk_sequence_error`, `timeout`); others are raised as raw `MeshError(code="...", ...)` (`connection_failed`, `handler_error`, `not_found`). The split is historical, not principled.
- The handler dispatch in `_mesh.py` has a single outer `except Exception` that wraps anything non-`MeshError` as `code="handler_error"`. This conflates two distinct failure modes:
  - **Caller fault** — input doesn't validate against the agent's schema. `pydantic.ValidationError` is raised by `info.input_adapter.validate_json()` before the handler body runs.
  - **Provider fault** — the handler ran and threw.
  The wire surfaces both as `handler_error`, so callers cannot distinguish "I sent bad data" from "the agent is broken."
- The streaming path duplicates the timeout error: `_invocation.py:114` raises `MeshError(code="timeout", ...)` directly instead of `MeshTimeout`. Drift, not by design.

The audit of v1.0 (`.planning/v1.0-MILESTONE-AUDIT.md`) flagged the validation/handler conflation as the only remaining substantive code gap. This ADR resolves that gap and, in the same change, consolidates the error surface so future categorical errors have an obvious home.

## Decision

### 1. Move all error classes to a dedicated `_errors` module

`src/openagentmesh/_errors.py` becomes the single home for the base exception and every categorical subclass. `_models.py` keeps only Pydantic models.

Public re-exports from `openagentmesh.__init__` are preserved verbatim — this is an internal restructure, not a public API change.

```python
# src/openagentmesh/__init__.py  (no behavior change)
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
```

### 2. Error class hierarchy

`MeshError` stays the base. Every code becomes a subclass. No more raw `MeshError(code="...")` constructions in production code paths.

```
MeshError                  # base; any-error catch via `except MeshError`
├── InvalidInput           # NEW — caller's input failed schema validation
├── HandlerError           # uncategorized exception inside agent handler
├── InvocationMismatch     # ADR-0047 — wrong verb for shape
├── NotFound               # promoted from raw `code="not_found"`
├── ConnectionFailed       # promoted from raw `code="connection_failed"`
├── MeshTimeout            # ADR-0034 — name preserved, not renamed
└── ChunkSequenceError     # ADR-0005 — stream ordering
```

Class names follow the no-suffix convention established by the recent ADRs (`InvocationMismatch`, `MeshTimeout`, `NotFound`, `ConnectionFailed`). The wire `code` is independent of the class name — see code taxonomy below.

### 3. Code taxonomy

| Code                    | Class                | Raised when                                                         | Caller action                          |
|-------------------------|----------------------|---------------------------------------------------------------------|----------------------------------------|
| `invalid_input`         | `InvalidInput`       | Input fails `info.input_adapter.validate_json()`                    | Fix the payload; do not retry as-is    |
| `handler_error`         | `HandlerError`       | Handler body raised any non-`MeshError` exception                   | Treat as opaque agent failure          |
| `invocation_mismatch`   | `InvocationMismatch` | `call`/`stream`/`send` doesn't match agent's invocable/streaming    | Use the correct verb                   |
| `not_found`             | `NotFound`           | Agent missing from registry / catalog                               | Fix the name; check catalog            |
| `connection_failed`     | `ConnectionFailed`   | Initial NATS connect or reconnect fails                             | Check transport / URL                  |
| `timeout`               | `MeshTimeout`        | No reply within deadline                                            | Retry with backoff or raise SLA        |
| `chunk_sequence_error`  | `ChunkSequenceError` | Stream chunks arrive out of order (defensive)                       | Treat as transport bug                 |

Codes are stable wire identifiers. Classes are local Python conveniences. By default the code is the snake_case of the class name (`InvalidInput` → `invalid_input`, `HandlerError` → `handler_error`). The one asymmetric pair is `MeshTimeout` → `timeout`: dropping the redundant `mesh_` prefix on a single-word code reads better than `mesh_timeout`. Symmetry is the rule; the timeout case is the documented exception.

Adding a new code requires either an existing subclass or a new one in `_errors.py`; raw `MeshError(code="new_thing", ...)` is disallowed in `src/`.

### 4. Dispatch in `_mesh.py`

The single outer `try/except` is replaced with a two-stage structure that separates input validation from handler execution.

```python
async def handler(msg: nats.aio.msg.Msg) -> None:
    request_id = msg.headers.get("X-Mesh-Request-Id", "") if msg.headers else ""
    wants_stream = msg.headers and msg.headers.get("X-Mesh-Stream") == "true"

    try:
        # Pre-flight verb/shape check (ADR-0047)
        if wants_stream and not info.streaming:
            raise InvocationMismatch(agent=name, request_id=request_id, message=...)
        if not wants_stream and info.streaming:
            raise InvocationMismatch(agent=name, request_id=request_id, message=...)

        # Input validation step — caller-fault errors stop here
        try:
            payload = info.input_adapter.validate_json(msg.data) if info.input_adapter and msg.data else None
        except pydantic.ValidationError as ve:
            raise InvalidInput(
                agent=name,
                request_id=request_id,
                message=f"Input failed validation for agent '{name}'",
                details={"errors": ve.errors()},
            ) from ve

        # Handler execution — provider-fault errors land here
        try:
            if info.streaming:
                await self._handle_streaming(msg, info, name, request_id, payload)
            else:
                await self._handle_responder(msg, info, name, request_id, payload)
        except MeshError:
            raise  # categorical error from inside handler — pass through
        except Exception as e:
            raise HandlerError(
                agent=name,
                request_id=request_id,
                message=str(e),
            ) from e

    except MeshError as error:
        # Single error-publishing path (unchanged from current)
        await self._publish_error(error, msg, wants_stream, request_id, name)
```

`_handle_responder` and `_handle_streaming` accept the already-validated payload, so the validation step is no longer duplicated inside them.

### 5. Class signatures

All subclasses take a uniform constructor shape. Where details matter (`InvalidInput`, `ChunkSequenceError`), they are typed.

```python
class MeshError(Exception):
    """Base for all mesh errors. Carries the wire envelope (ADR-0001)."""

    code: ClassVar[str] = "mesh_error"  # base default, never emitted directly

    def __init__(
        self,
        *,
        message: str,
        agent: str = "",
        request_id: str = "",
        details: dict[str, Any] | None = None,
        code: str | None = None,  # only for back-compat / wire deserialization
    ):
        super().__init__(message)
        self.code = code or self.__class__.code
        self.message = message
        self.agent = agent
        self.request_id = request_id
        self.details = details or {}


class InvalidInput(MeshError):
    code: ClassVar[str] = "invalid_input"

    def __init__(self, *, agent: str = "", request_id: str = "",
                 message: str = "Input validation failed",
                 details: dict[str, Any] | None = None):
        super().__init__(message=message, agent=agent, request_id=request_id, details=details)


class HandlerError(MeshError):
    code: ClassVar[str] = "handler_error"
    # constructor identical to InvalidInput shape


class NotFound(MeshError):
    code: ClassVar[str] = "not_found"

    def __init__(self, *, agent: str, request_id: str = ""):
        super().__init__(
            message=f"Agent '{agent}' not found",
            agent=agent,
            request_id=request_id,
        )


class ConnectionFailed(MeshError):
    code: ClassVar[str] = "connection_failed"
    # constructor identical to base


# Existing subclasses — preserved with class-level `code` attribute
class InvocationMismatch(MeshError):
    code: ClassVar[str] = "invocation_mismatch"

class MeshTimeout(MeshError):
    code: ClassVar[str] = "timeout"

class ChunkSequenceError(MeshError):
    code: ClassVar[str] = "chunk_sequence_error"
```

`code` as a `ClassVar` lets the constructor default it from the subclass, removing the boilerplate of every `__init__` passing the literal again. Wire deserialization can still override via the `code=` kwarg.

### 6. Wire-side deserialization

When the SDK receives an error envelope on the wire, it reconstructs the matching subclass by code:

```python
_CODE_TO_CLASS: dict[str, type[MeshError]] = {
    cls.code: cls for cls in (
        InvalidInput, HandlerError, InvocationMismatch,
        NotFound, ConnectionFailed, MeshTimeout, ChunkSequenceError,
    )
}

def from_envelope(payload: dict) -> MeshError:
    code = payload.get("code", "mesh_error")
    klass = _CODE_TO_CLASS.get(code, MeshError)
    return klass(
        message=payload.get("message", ""),
        agent=payload.get("agent", ""),
        request_id=payload.get("request_id", ""),
        details=payload.get("details") or {},
        code=code if klass is MeshError else None,
    )
```

This means a remote agent's `InvalidInput` is caught locally as `except InvalidInput`, not just as `except MeshError`.

### 7. Migration scope

Files touched:

- `_models.py`: remove the four exception classes; keep Pydantic models only.
- `_errors.py`: NEW.
- `__init__.py`: change import source; preserve `__all__`.
- `_mesh.py`: refactor `handler` dispatch; replace `MeshError(code="connection_failed", ...)` → `ConnectionFailed(...)`; replace catch-all wrap → `HandlerError(...)`.
- `_invocation.py`: replace `MeshError(code="timeout", ...)` → `MeshTimeout(...)`; remove dead `MeshError` code-string raises.
- `_discovery.py`: replace `MeshError(code="not_found", ...)` → `NotFound(agent=name)`.
- `cli/agent.py`: existing `except MeshError` blocks already work; optionally tighten to `except NotFound` / `except ValidationError` for richer hints.
- Tests: existing tests that assert on `code` keep working because codes are unchanged. Tests that catch `MeshError` keep working. New tests added for the validation/handler split.

No changes to: wire format, NATS subject layout, public method signatures, contract schema.

## Code sample (DX contract)

What a caller sees today vs. after this ADR:

**Before:**
```python
try:
    result = await mesh.call("scorer", {"profile": ...})  # bad payload shape
except MeshError as e:
    if e.code == "handler_error":
        # Was it my bad input, or did the agent crash? Have to grep e.message.
        ...
```

**After:**
```python
from openagentmesh import InvalidInput, HandlerError, MeshError

try:
    result = await mesh.call("scorer", {"profile": ...})
except InvalidInput as e:
    # Caller fault — fix the payload, surface to user, don't retry.
    print(e.details["errors"])  # pydantic-style error list
except HandlerError as e:
    # Provider fault — log, retry with backoff, or fall back.
    metrics.incr("scorer.handler_error")
except MeshError:
    # Anything else categorically.
    raise
```

## Alternatives Considered

**Single `errors/` package with one file per category.** Rejected. Five to seven classes don't justify the import boilerplate or the directory. Existing convention is single underscored modules (`_handler.py`, `_subjects.py`, `_invocation.py`); a flat `_errors.py` matches. Easy to promote to a package later if the taxonomy grows past ~15 classes.

**Keep `_models.py` as the home, just add `InvalidInput` there.** Rejected. `_models.py` already mixes Pydantic models with exceptions; adding more aggravates the smell. The cost of moving four classes is ~20 lines of import diff in three files.

**Catch `pydantic.ValidationError` only — don't add a dedicated subclass.** Rejected. The wire envelope needs a stable `code` regardless of the local Python type, and remote callers reconstructing from JSON need a class to attach to. Symmetry with `InvocationMismatch`, `MeshTimeout`, `ChunkSequenceError` is also worth more than saving one class definition.

**Name the new class `ValidationError`.** Rejected — collides with `pydantic.ValidationError`, which is imported in essentially every file in this codebase that touches Pydantic. Two `ValidationError` symbols in the same module would shadow each other depending on import order and make `except ValidationError:` ambiguous to readers. Same precedent set by ADR-0034: `MeshTimeout` was chosen over `TimeoutError` to avoid the builtin collision; here the collision with the third-party type is even more frequent. `InvalidInput` follows the no-suffix convention of the surrounding ADRs (`InvocationMismatch`, `NotFound`, `ConnectionFailed`) and reads naturally at call sites.

**Name the new class `MeshValidationError`.** Rejected. Solves the collision but reads heavily and breaks the no-suffix convention used by the four most recent error-related ADRs.

**Rename `MeshTimeout` → `TimeoutError`.** Rejected (out of scope). ADR-0034 chose `MeshTimeout` deliberately to avoid colliding with the builtin `TimeoutError`. Renaming is a separate decision, not a side-effect of this restructure.

**Keep `not_found` and `connection_failed` as raw `MeshError(code=...)` calls.** Rejected. The principle "every code has a class" is what makes the `_CODE_TO_CLASS` table tractable. Two more class definitions for ~5 lines each is cheap; the consistency for downstream callers is worth it.

**Auto-generate `_CODE_TO_CLASS` via `__init_subclass__`.** Considered. Slightly cleaner but obscures the registry from grepping. The manual dict is six lines and reads clearly. Optimization deferred until the taxonomy is large enough to feel the pain.

## Consequences

- New public symbols: `InvalidInput`, `HandlerError`, `NotFound`, `ConnectionFailed`. Listed in `__all__` and in the API reference.
- Wire codes unchanged. No breaking change for any caller who matches on `e.code`.
- The previous CLI-side hint logic (`cli/agent.py:_cli_hint`) can simplify: `isinstance(exc, NotFound)` instead of `exc.code == "not_found"`. Optional follow-up.
- Future categorical errors enter via `_errors.py` only. Code review can enforce "no raw `MeshError(code=...)` outside `_errors.py` and wire deserialization."
- Closes original v1 requirement TRAN-05 (input validation surfaces with its own code, no longer conflated with `handler_error`). Note: the TRAN-05 wording prescribed `validation_error` as the code; this ADR adopts `invalid_input` instead for symmetry with the class name. REQUIREMENTS.md should be updated accordingly when reconciled.
- Tests must add at least: (a) malformed payload → `InvalidInput` on caller, (b) handler raising → `HandlerError` on caller, (c) wire deserialization round-trip preserves subclass identity.

## Open items (out of scope)

- Should the `details` payload of `InvalidInput` follow a stable schema (e.g., the pydantic `errors()` shape) so cross-language clients can parse it? Defer to ADR-0001 amendment if/when a non-Python client appears.
- `HandlerError` currently leaks `str(e)` in `message`. For sensitive deployments, an option to redact handler-side messages may be useful. Defer until requested.
