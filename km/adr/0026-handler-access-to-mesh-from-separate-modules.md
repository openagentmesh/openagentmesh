# ADR-0026: Handler access to mesh services from separate modules

- **Type:** api-design
- **Date:** 2026-04-14
- **Status:** discussion
- **Source:** conversation (cookbook design discussion on multi-agent coordination use cases)

## Context

Cookbook recipes that use `mesh.workspace` and `mesh.context` from inside handler functions expose a structural gap in the current API design.

The `@mesh.agent` decorator binds an async function to a specific `AgentMesh` instance:

```python
mesh = AgentMesh()

@mesh.agent(name="researcher", channel="analysts", description="...")
async def research(req: ResearchInput) -> ResearchOutput:
    # How does this function access mesh.context or mesh.workspace?
    ...
```

In a single-file script, `research` closes over the module-level `mesh` variable and can call `mesh.context.get(...)` directly. This works but is implicit — the handler depends on a name in its enclosing scope, not on anything the SDK provides or enforces.

In a real multi-module project, agent handlers live in separate files (`agents/researcher.py`, `agents/refiner.py`, etc.). Accessing `mesh` from inside those handlers requires either importing a shared `mesh` singleton from a central module, or the SDK providing a mechanism to inject it.

This decision affects how every cookbook recipe beyond trivial request/reply is structured. It also determines whether `mesh.workspace` and `mesh.context` are truly first-class features or bolt-ons that require workarounds.

## Options

### Option A: Closure over shared module-level instance (current implicit model)

The developer exports `mesh` from a shared module (`mesh.py` or `app.py`). Handlers import it:

```python
# mesh.py
from openagentmesh import AgentMesh
mesh = AgentMesh()

# agents/researcher.py
from mesh import mesh

@mesh.agent(name="researcher", channel="analysts", description="...")
async def research(req: ResearchInput) -> ResearchOutput:
    tasks = await mesh.context.get("project/tasks", model=TaskList)
    ...
```

No SDK changes required. This is idiomatic Python for shared singletons (analogous to a shared SQLAlchemy `Session` or a shared `httpx.AsyncClient`). The pattern is well understood and explicit.

Downside: `mesh` is a module-level singleton. Tests that want to use a different `mesh` instance (e.g., `AgentMesh.local()`) cannot rebind the handlers without re-importing or monkeypatching. The `@mesh.agent` decorator captures the instance at decoration time.

### Option B: Explicit injection via a second handler parameter

The SDK detects a second parameter named `ctx` (or typed as `MeshContext`) and injects a context object carrying references to the current mesh services:

```python
from openagentmesh import AgentMesh, MeshContext

@mesh.agent(name="researcher", channel="analysts", description="...")
async def research(req: ResearchInput, ctx: MeshContext) -> ResearchOutput:
    tasks = await ctx.context.get("project/tasks", model=TaskList)
    artifact = await ctx.workspace.get(req.artifact_key)
    ...
```

`MeshContext` is a lightweight object wrapping `mesh.context`, `mesh.workspace`, and possibly `mesh.call` (for agent-to-agent calls from within a handler). The SDK inspects the handler signature at registration time and injects it if present. Handlers that don't need mesh services keep the single-parameter signature.

Testable without mocking the global `mesh`: pass a mock `MeshContext` directly. Clean separation between the agent's inputs (`req`) and its infrastructure access (`ctx`).

Downside: introduces a new concept (`MeshContext`) and SDK introspection of handler parameters. Breaks the "function-first, no magic" philosophy slightly — the handler now has an implicit second argument.

### Option C: `req.mesh` — request object carries mesh reference

Wrap the incoming payload in a richer request object that includes a reference to the mesh:

```python
@mesh.agent(name="researcher", channel="analysts", description="...")
async def research(req: ResearchInput) -> ResearchOutput:
    tasks = await req.mesh.context.get("project/tasks", model=TaskList)
    ...
```

`req` is still a `ResearchInput` Pydantic model; `req.mesh` is injected by the SDK before dispatching. Accessing mesh services via the request object keeps the handler signature minimal.

Downside: pollutes the domain model (`ResearchInput`) with infrastructure. A Pydantic model carrying a `mesh` attribute is unexpected and won't validate cleanly. This would require `ResearchInput` to allow extra fields or a separate injection mechanism, making it more magical than Option B.

## Open Questions

- Is the shared singleton (Option A) sufficient for the real-world use cases, or will test isolation be a practical blocker?
- Does Option B's `MeshContext` parameter conflict with the "one parameter, typed input" DX that the quickstart and cookbook recipes establish?
- Should agent-to-agent calls from inside a handler (`mesh.call("other-agent", ...)`) be available on `MeshContext`, or is that always via the global `mesh`?
