# Coding Conventions

**Analysis Date:** 2026-05-08

## Naming Patterns

**Files:**
- Modules use lowercase with underscores: `_mesh.py`, `_handler.py`, `_invocation.py`
- Private/internal modules prefixed with underscore: `_errors.py`, `_models.py`, `_local.py`
- Public package exports via `__init__.py` with explicit `__all__`
- CLI submodules use descriptive names without underscore: `mesh.py`, `agent.py`, `demo.py`

**Functions and Methods:**
- Use snake_case: `inspect_handler()`, `from_envelope()`, `_resolve_subject()`
- Private methods prefixed with underscore: `_check_capability()`, `_serialize_payload()`, `_start_catalog_watcher()`
- Async functions and coroutines use same naming as sync: `async def call()`, `async def catalog()`
- Handlers follow pattern: handler body is user code, not SDK concern. Shape inspection via `inspect_handler(func)`

**Variables:**
- Local variables use snake_case: `request_id`, `stream_subject`, `chunk_handler`
- Module-level constants use UPPERCASE: `AGENTMESH_DIR`, `NATS_VERSION`, `_CATALOG_BUCKET`
- Private module state prefixed with underscore: `_nc` (NATS client), `_js` (JetStream context), `_agents` (registered agents dict)

**Types:**
- Pydantic models use PascalCase: `AgentMesh`, `AgentSpec`, `CatalogEntry`, `AgentContract`, `MeshError`, `InvalidInput`
- Type hints on function parameters and returns (not optional except where None is valid)
- Use `from __future__ import annotations` for forward references and deferred evaluation

## Code Style

**Formatting:**
- Tool: `ruff` (formatter/linter)
- Line length: 100 characters (configured in `pyproject.toml`)
- No .prettierrc or separate formatter; ruff handles all formatting

**Linting:**
- Tool: `ruff` (Rust-based)
- Active rules: `E` (PEP 8 errors), `F` (Pyflakes), `I` (isort), `UP` (upgrade syntax), `B` (flake8-bugbear), `SIM` (simplify)
- Ignored: `E501` (line length — handled by formatter, not lint)
- Target: Python 3.11+ (`target-version = "py311"`)
- Configuration: `pyproject.toml` sections `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.lint.isort]`

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first if used)
2. Standard library: `import asyncio`, `import json`, `import logging`, `from pathlib import Path`
3. Third-party: `import nats`, `import pydantic`, `from pydantic import BaseModel`
4. Internal: `from ._mesh import AgentMesh`, `from ._errors import InvalidInput`
5. TYPE_CHECKING block: `if TYPE_CHECKING: from ._mesh import AgentMesh` (for circular dependency avoidance)

**Path Aliases:**
- Internal imports use relative module paths: `from ._models import AgentSpec` (not absolute `openagentmesh._models`)
- Public exports re-exported in `__init__.py`: clients import `from openagentmesh import AgentMesh`

Example from `src/openagentmesh/_invocation.py`:
```python
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import nats

from ._errors import ChunkSequenceError, MeshError, MeshTimeout, from_envelope

if TYPE_CHECKING:
    from ._mesh import AgentMesh
```

## Error Handling

**Patterns:**
- Use `MeshError` and its categorical subclasses (`InvalidInput`, `HandlerError`, `NotFound`, `ConnectionFailed`, `InvocationMismatch`, `MeshTimeout`, `ChunkSequenceError`)
- Each error has a `code` ClassVar for wire serialization (ADR-0057)
- Errors carry wire envelope: `code`, `message`, `agent`, `request_id`, `details`
- `from_envelope(payload)` reconstructs correct subclass from wire (enables remote errors to preserve type identity)
- Catch specific subclasses: `except InvalidInput:` not just `except MeshError:`
- Never raise plain `MeshError` — use a categorical subclass (or return unknown code for forward compatibility)

Example from `src/openagentmesh/_errors.py`:
```python
class InvalidInput(MeshError):
    """Caller's input failed schema validation."""
    code: ClassVar[str] = "invalid_input"

def from_envelope(payload: dict[str, Any]) -> MeshError:
    """Reconstruct the matching `MeshError` subclass from a wire envelope."""
    code = payload.get("code", "mesh_error")
    klass = _CODE_TO_CLASS.get(code)
    # ... unknown codes deserialize to MeshError with wire code preserved
```

## Logging

**Framework:** `logging` (Python standard library)

**Patterns:**
- Each module defines a logger: `_log = logging.getLogger("openagentmesh")`
- Log at module level for debugging/observability: `_log.debug()`, `_log.info()`, `_log.warning()`, `_log.error()`
- No hardcoded print statements for user-facing output (use logging or CLI output helpers)
- NATS errors logged via error callback: `async def _nats_error_cb(self, e: Exception)`

Example from `src/openagentmesh/_mesh.py`:
```python
import logging

_log = logging.getLogger("openagentmesh")

async def _nats_error_cb(self, e: Exception) -> None:
    _log.error(f"NATS error: {e}")
```

## Comments

**When to Comment:**
- Comments explain *why*, not what the code does
- Docstrings on public classes and methods (not internal helpers)
- Inline comments for non-obvious logic or workarounds
- No commented-out code blocks; use version control instead

**Docstrings:**
- Google-style docstrings (not NumPy or Sphinx style)
- One-liner for simple functions: `"""Synchronous request/reply. Returns the response as a dict."""`
- Multi-paragraph for complex behavior, with code examples in public APIs

Example from `src/openagentmesh/_mesh.py`:
```python
class AgentMesh(InvocationMixin, DiscoveryMixin):
    """Client and host for OpenAgentMesh agents.

    Use as an async context manager::

        mesh = AgentMesh()

        @mesh.agent(spec)
        async def echo(req: EchoInput) -> EchoOutput: ...

        async with mesh:
            result = await mesh.call("echo", {"message": "hi"})

    For tests and demos::

        async with AgentMesh.local() as mesh:
            ...
    """
```

## Function Design

**Size:** 
- Target: under 50 lines per function (soft guideline)
- Extract helpers for complex logic (mixins and internal helpers are encouraged)

**Parameters:**
- Positional args for required parameters: `def call(self, name: str, payload: Any = None)`
- Keyword-only args for optional config: `timeout: float = 30.0`
- Type hints always present (use `Any` if truly dynamic)
- Default values for optional parameters

**Return Values:**
- Explicit return type hints: `-> dict`, `-> AsyncIterator[dict]`, `-> list[CatalogEntry]`
- Async functions return awaitable, not Task
- Streaming/generator functions use `async def` + `yield` or `async def` + `AsyncIterator[T]` annotation

Example from `src/openagentmesh/_invocation.py`:
```python
async def call(self: AgentMesh, name: str, payload: Any = None, timeout: float = 30.0) -> dict:
    """Synchronous request/reply. Returns the response as a dict."""
    ...

async def stream(
    self: AgentMesh, name: str, payload: Any = None, timeout: float = 60.0
) -> AsyncIterator[dict]:
    """Streaming request. Yields response chunks as dicts."""
    ...
```

## Module Design

**Exports:**
- Public symbols listed in `__all__` in `__init__.py`
- Internal/private modules (prefixed with `_`) not exported; used only internally
- Public API is narrow: `AgentMesh`, `AgentSpec`, `CatalogEntry`, `AgentContract`, error subclasses

**Barrel Files:**
- `src/openagentmesh/__init__.py` is the public entry point
- CLI subcommands in `src/openagentmesh/cli/__init__.py` assembles typer app
- Demos not exported; used via `from openagentmesh.demos.hello_world import main`

**Mixins:**
- `InvocationMixin`: implements `call()`, `stream()`, `send()`, `subscribe()`
- `DiscoveryMixin`: implements `catalog()`, `contract()`, `discover()`
- Both mixed into `AgentMesh` for clean separation of concerns

---

*Convention analysis: 2026-05-08*
