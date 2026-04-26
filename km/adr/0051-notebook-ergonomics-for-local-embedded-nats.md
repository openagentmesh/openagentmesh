# ADR-0051: Notebook ergonomics for `AgentMesh.local()` (sync entry, atexit, idempotent reuse)

- **Type:** api-design
- **Date:** 2026-04-25
- **Status:** discussion
- **Source:** conversation (notebook compatibility question, benchmark against ChromaDB / FastAPI / Ray / Dask / redislite)

## Context

`AgentMesh.local()` is currently an async context manager (ADR-0022). It works in pytest and single-file scripts. It does not work well in Jupyter notebooks because:

1. **Cells are not blocks.** A single `async with AgentMesh.local() as mesh:` cannot span cells in the natural notebook idiom (one cell at a time, persistent state). Users either cram a whole demo into one cell or manually drive `__aenter__` / `__aexit__`, which exposes dunders.
2. **Kernel restarts leak the NATS subprocess.** `EmbeddedNats.start()` spawns NATS with `start_new_session=True`. A hard kernel restart skips `__aexit__`. The NATS process keeps running, the port stays bound, and `~/.agentmesh/data/embedded-<port>/` accumulates.
3. **Re-running the same cell leaks more servers.** Every re-execution of a cell that calls `AgentMesh.local()` spawns a new NATS subprocess on a new port. The previous one is orphaned if the prior context did not exit cleanly.
4. **No connection visibility.** `EmbeddedNats` picks a random free port. The user sees nothing in cell output and has to inspect `mesh._url`.

Notebooks are a credible distribution channel for an SDK like OAM (LLM tool selection demos, data-science-flavored agent flows). Right now they are second-class.

### How peers handle this

| Tool                | Worker model              | Notebook story                                                                |
| ------------------- | ------------------------- | ----------------------------------------------------------------------------- |
| **ChromaDB**        | In-process (SQLite)       | Trivial. No subprocess.                                                       |
| **DuckDB / Polars** | In-process                | Trivial.                                                                      |
| **FastAPI** typical | External `uvicorn`        | Server in terminal, notebook is HTTP client. Clean.                           |
| **Ray** (`init`)    | Multi-process subprocess  | Sync `init()`, `atexit` cleanup, idempotent reuse, prints connection info.    |
| **Dask** (`Client`) | Multi-process             | Sync constructor, `client.close()`, `atexit`, repr shows dashboard URL.       |
| **redislite**       | Embedded Redis subprocess | Sync constructor, `atexit` kills subprocess.                                  |
| **Streamlit**       | Background daemon thread  | Thread dies with kernel.                                                      |
| **OAM today**       | NATS subprocess           | Async context manager; cannot span cells; kernel restart leaks; no visibility. |

The closest precedent is **redislite**: embedded binary, atexit-driven cleanup. The closest UX target is **Ray**: sync entry, idempotent, visible connection info.

## Decision

Add a notebook-friendly entry point alongside the existing async context manager, plus three lifecycle improvements that benefit all callers.

### 1. New entry point: `AgentMesh.local_started()`

Returns a started `AgentMesh` (NATS running, buckets created, watcher started) instead of a context manager. Lifecycle is owned by an `atexit` handler and an explicit `mesh.stop()`.

```python
# Notebook cell 1
mesh = await AgentMesh.local_started()

@mesh.agent(spec)
async def echo(req: EchoInput) -> EchoOutput: ...

# Notebook cell 2 (later)
result = await mesh.call("echo", {"message": "hi"})

# Notebook cell 3 (optional, atexit handles it otherwise)
await mesh.stop()
```

The existing `async with AgentMesh.local() as mesh:` stays unchanged for tests and scripts.

### 2. Idempotent reuse within a process

If `local_started()` is called twice in the same Python process, the second call reuses the existing embedded NATS instead of spawning a second one. A module-level singleton (`_active_embedded: EmbeddedNats | None`) tracks the running server. The new `AgentMesh` is a fresh client connected to the same URL.

This makes "re-run the cell" safe.

### 3. `atexit` cleanup in `EmbeddedNats`

`EmbeddedNats.start()` registers `atexit.register(self.stop_sync)`. On normal interpreter shutdown (including kernel restart through ipykernel's atexit chain), the NATS subprocess and data directory are torn down.

`stop_sync` is a small synchronous variant of `stop()` that calls `terminate()` + `wait(timeout=5)` + `shutil.rmtree`. atexit handlers cannot be coroutines.

### 4. Connection visibility on the constructor

When `AgentMesh` is constructed (any path), it prints the connection target on first instantiation. Repr includes the URL:

```
>>> mesh = AgentMesh()
<AgentMesh url=nats://localhost:4222 status=disconnected>

>>> mesh = await AgentMesh.local_started()
[openagentmesh] embedded NATS at nats://127.0.0.1:54321
<AgentMesh url=nats://127.0.0.1:54321 status=connected agents=0>
```

`mesh.url` becomes a documented public read-only property. (This sub-change ships independently of the ADR per the conversation; it is recorded here for completeness.)

## Alternatives Considered

- **Cross-process lockfile reuse** (one embedded NATS shared across notebooks). Rejected for now: adds refcount + PID liveness logic, and the multi-process story is already covered cleanly by `agentmesh up`. Revisit if users complain.
- **Background-thread server** (Streamlit pattern). Rejected: NATS is a binary, not a Python server. We would still spawn a subprocess and gain nothing.
- **Drop `local()` entirely, force `agentmesh up` for notebooks.** Rejected: zero-config is a real DX win for tutorials and screencasts. We just need it to behave well.
- **Use `nest_asyncio` to make `asyncio.run` work in notebooks.** Rejected: `nest_asyncio` is invasive and our context manager is async natively; IPython supports top-level `await` since 7.0. The fix is API shape, not loop manipulation.
- **Detect Jupyter and switch behavior implicitly.** Rejected: implicit branching by environment is a debugging trap. Two named entry points are clearer.

## Risks and Implications

- `local_started()` introduces a second lifecycle pattern. Docs must be unambiguous: context manager for tests/scripts, `local_started()` for notebooks/REPL.
- `atexit` ordering is not guaranteed across libraries. If the user opens NATS clients in their own atexit handlers, ordering could matter. Acceptable: NATS clients tolerate the server going away (fail-fast), and the SDK's own teardown registers before user code runs.
- Idempotent reuse means a cell that intentionally wants a fresh NATS (e.g., to test a clean state) needs an explicit `await mesh.stop()` before re-entering. Document this.
- Printing on construction is mildly noisy. Suppressible via a `quiet=True` flag if it bothers anyone; default is on because Ray/Dask have proven users want it.

## Code Sample (DX Contract)

```python
# In a notebook
from openagentmesh import AgentMesh, AgentSpec
from pydantic import BaseModel

class EchoInput(BaseModel):
    message: str

class EchoOutput(BaseModel):
    reply: str

# Cell 1: start mesh
mesh = await AgentMesh.local_started()
# [openagentmesh] embedded NATS at nats://127.0.0.1:54321

# Cell 2: register agent
@mesh.agent(AgentSpec(name="echo", description="echoes back"))
async def echo(req: EchoInput) -> EchoOutput:
    return EchoOutput(reply=req.message)

# Cell 3: invoke
result = await mesh.call("echo", {"message": "hi"})
# EchoOutput(reply='hi')

# Cell 4 (re-run safe): same NATS reused
mesh2 = await AgentMesh.local_started()
assert mesh2.url == mesh.url

# Kernel restart now: atexit kills NATS, removes data dir.
```
