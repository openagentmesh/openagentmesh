# Testing Patterns

**Analysis Date:** 2026-05-08

## Test Framework

**Runner:**
- `pytest` (9.0.2+)
- Config: `pyproject.toml` section `[tool.pytest.ini_options]`
- Async support: `pytest-asyncio` (1.3.0+) with `asyncio_mode = "auto"`

**Assertion Library:**
- Python built-in `assert` statements
- Pydantic `ValidationError` for schema failures
- `pytest.raises()` for exception testing

**Run Commands:**
```bash
pytest tests/                   # Run all tests
pytest tests/test_mesh.py       # Run single test file
pytest tests/test_mesh.py::TestHelloWorld::test_register_and_call  # Run specific test
pytest --co                     # List all tests (no run)
pytest -v                       # Verbose output
pytest -x                       # Stop on first failure
```

## Test File Organization

**Location:**
- Tests co-located in `tests/` directory (parallel to `src/`)
- Nested subdirectories: `tests/cookbook/`, `tests/cli/`
- No `conftest.py` (no shared fixtures; each test is self-contained)

**Naming:**
- Files: `test_*.py` (not `*_test.py`)
- Classes: `Test*` (PascalCase, starts with "Test")
- Methods: `test_*` (snake_case, starts with "test_")
- Example: `test_mesh.py` → `TestHelloWorld` → `test_register_and_call()`

**Structure:**
```
tests/
├── test_mesh.py           # Core AgentMesh integration tests
├── test_models.py         # AgentSpec, CatalogEntry, handler inspection
├── test_errors_taxonomy.py # Error hierarchy and wire serialization
├── test_subscribe.py      # Subscription patterns (raw subject + agent)
├── test_async_callback.py # Async callbacks (on_reply, on_error)
├── test_workspace.py      # Object Store (artifacts)
├── test_tool_conversion.py # Tool schema generation
├── test_publisher.py      # Publisher pattern (yield + subscribe)
├── test_cli_demo.py       # CLI smoke test
├── cli/
│   ├── __init__.py
│   ├── test_smoke.py      # CLI invocation tests
│   ├── test_output.py     # CLI output formatting
│   └── test_config.py     # CLI config/URL resolution
└── cookbook/
    ├── __init__.py
    ├── test_multi_process.py    # Multi-process provider/consumer recipe
    ├── test_llm_tool_selection.py # LLM discovers and calls agents
    ├── test_error_handling.py    # Error handling patterns
    ├── test_load_balancing.py    # Queue group load balancing
    ├── test_reactive_pipeline.py # Pub/sub reactive pipeline
    └── test_shared_plan.py       # Multi-agent planning with shared state
```

## Test Structure

**Suite Organization:**
```python
"""Tests for mesh.subscribe() with raw subject support (ADR-0034).

Exercises the async generator subscription pattern using direct
NATS publish to simulate event sources.
"""

import asyncio
import pytest
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, MeshError


class EchoOutput(BaseModel):
    reply: str


# --- Raw subject subscription ---


class TestSubscribeRawSubject:
    async def test_receives_message_on_subject(self):
        """subscribe(subject=) yields a JSON message when stream-end is set."""
        # arrange
        subject = "test.events.single"

        # act
        async with AgentMesh.local() as mesh:
            # ... setup and assertions
            assert result == expected

    async def test_timeout_raises_mesh_timeout(self):
        """No messages within timeout raises MeshTimeout."""
        # arrange
        subject = "test.events.silent"

        # act + assert
        with pytest.raises(MeshTimeout):
            async for _ in mesh.subscribe(subject=subject, timeout=0.2):
                pass
```

**Patterns:**
- Module docstring at top: explains what the test file covers and which ADRs
- Test models (Pydantic) defined at module level: `class EchoInput(BaseModel)`, `class EchoOutput(BaseModel)`
- Comments section headers with `# ---` dividers for logical groupings
- Test class groups related tests: `TestHelloWorld`, `TestCapabilityInference`, `TestCatalog`
- Each test method is `async def test_*`
- One assertion concept per test (tight focus)
- Docstring on each test method explaining what it validates

## Mocking

**Framework:** No mocking library (not imported in tests)

**Patterns:**
- Tests use `AgentMesh.local()` async context manager for embedded NATS
- No mocks of NATS client or JetStream; real infrastructure is lightweight and fast
- Handlers registered in test scope: handlers are test code, not mocked
- For pub/sub testing: use direct `mesh._nc.publish()` to inject events

Example from `tests/test_subscribe.py`:
```python
async def test_receives_message_on_subject(self):
    """subscribe(subject=) yields a JSON message when stream-end is set."""
    subject = "test.events.single"

    async with AgentMesh.local() as mesh:
        received = []

        async def publisher():
            await asyncio.sleep(0.05)
            await mesh._nc.publish(
                subject,
                json.dumps({"event": "hello"}).encode(),
                headers={
                    "X-Mesh-Stream-End": "true",
                },
            )

        async def subscriber():
            async for msg in mesh.subscribe(subject=subject):
                received.append(msg)

        await asyncio.gather(
            asyncio.wait_for(subscriber(), timeout=5.0),
            publisher(),
        )

        assert len(received) == 1
        assert received[0]["event"] == "hello"
```

**What to Mock:**
- Nothing (avoid mocks; prefer real embedded NATS)
- If external API is needed (e.g., OpenAI in demo), parametrize or skip test

**What NOT to Mock:**
- NATS client (too lightweight)
- AgentMesh internals (test end-to-end)
- Handler execution (test real handlers)

## Fixtures and Factories

**Test Data:**
- Models defined at module level (not in fixtures)
- Factories built in test methods (no factory library)
- Reuse across tests via class attributes or module-level defs

Example from `tests/test_mesh.py`:
```python
class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    reply: str


class SummarizeInput(BaseModel):
    text: str


class SummarizeChunk(BaseModel):
    delta: str


class TestHelloWorld:
    async def test_register_and_call(self):
        spec = AgentSpec(name="echo", description="Echoes messages")

        async with AgentMesh.local() as mesh:
            @mesh.agent(spec)
            async def echo(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=f"Echo: {req.message}")

            result = await mesh.call("echo", {"message": "hello"})
            assert result["reply"] == "Echo: hello"
```

**Location:**
- No `conftest.py` or fixtures directory
- Shared test models defined at module level
- Inline handler definitions in test methods (keeps test self-contained)

## Coverage

**Requirements:** None enforced (no CI gate, no coverage threshold)

**View Coverage:**
```bash
pytest --cov=openagentmesh tests/
pytest --cov=openagentmesh --cov-report=html tests/  # HTML report in htmlcov/
```

## Test Types

**Unit Tests:**
- Scope: Single function or class behavior in isolation
- Location: `tests/test_errors_taxonomy.py`, `tests/test_models.py`
- Pattern: No AgentMesh.local(); just instantiate model or call helper function
- Example:
  ```python
  class TestErrorClassHierarchy:
      def test_invalid_input_is_mesh_error(self):
          err = InvalidInput(agent="x", message="bad payload")
          assert isinstance(err, MeshError)
          assert err.code == "invalid_input"
  ```

**Integration Tests:**
- Scope: Multiple components working together (AgentMesh + handlers + messaging)
- Location: `tests/test_mesh.py`, `tests/test_subscribe.py`, `tests/test_workspace.py`
- Pattern: Use `async with AgentMesh.local() as mesh:` for embedded NATS
- Example:
  ```python
  async def test_register_and_call(self):
      spec = AgentSpec(name="echo", description="Echoes messages")
      async with AgentMesh.local() as mesh:
          @mesh.agent(spec)
          async def echo(req: EchoInput) -> EchoOutput:
              return EchoOutput(reply=f"Echo: {req.message}")
          result = await mesh.call("echo", {"message": "hello"})
          assert result["reply"] == "Echo: hello"
  ```

**E2E Tests:**
- Framework: None (not in scope for Phase 1)
- Alternative: Cookbook tests in `tests/cookbook/` exercise realistic multi-agent workflows
- Example from `tests/cookbook/test_multi_process.py`:
  ```python
  class TestMultiAgentRecipe:
      async def test_main_completes(self):
          async with AgentMesh.local() as mesh:
              await main(mesh)
  ```

## Common Patterns

**Async Testing:**
```python
# All test methods are async def (pytest-asyncio handles auto-discovery)
class TestAsync:
    async def test_call_returns_dict(self):
        async with AgentMesh.local() as mesh:
            @mesh.agent(AgentSpec(name="x", description="x"))
            async def handler(req: Input) -> Output:
                return Output(...)

            result = await mesh.call("x", {...})
            assert result == expected
```

**Error Testing:**
```python
# Using pytest.raises() for exception validation
async def test_missing_agent_raises_not_found(self):
    async with AgentMesh.local() as mesh:
        with pytest.raises(NotFound, match="missing"):
            await mesh.contract("missing")

# Testing specific subclass identity
async def test_invalid_input_distinct_from_handler_error(self):
    async with AgentMesh.local() as mesh:
        @mesh.agent(AgentSpec(name="strict", description="strict"))
        async def strict_handler(req: StrictInput) -> Output:
            return Output(...)

        # Invalid input raises InvalidInput (not HandlerError)
        with pytest.raises(InvalidInput):
            await mesh.call("strict", {"bad": "payload"})
```

**Concurrency in Tests:**
```python
# Using asyncio.gather() to coordinate publisher/subscriber patterns
async def test_stream_yields_chunks(self):
    async with AgentMesh.local() as mesh:
        @mesh.agent(AgentSpec(name="streamer", description="streamer"))
        async def streamer(req: Input) -> Chunk:
            for item in items:
                yield Chunk(delta=item)

        chunks = []

        async def subscriber():
            async for chunk in mesh.stream("streamer", {...}):
                chunks.append(chunk)

        await asyncio.gather(
            asyncio.wait_for(subscriber(), timeout=5.0),
            asyncio.sleep(0.05),  # Let subscriber subscribe first
        )

        assert len(chunks) == len(items)
```

---

*Testing analysis: 2026-05-08*
