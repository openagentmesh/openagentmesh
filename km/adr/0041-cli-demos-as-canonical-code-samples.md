# ADR-0041: CLI demos as canonical code samples

## Status

documented

## Context

Code samples currently exist in up to three places: the ADR body, `docs/cookbook/`, and `tests/cookbook/`. Keeping them in sync is a maintenance burden, and divergence is inevitable. Meanwhile, users reading the docs have no way to run the code without copy-pasting it.

ADR-0033 established the `oam` CLI. Adding a `oam demo` subcommand gives users a one-command way to run any cookbook recipe against a local mesh. The question is where the canonical source of truth for that code lives.

## Decision

### Single canonical source

Each cookbook recipe is a Python module under `src/openagentmesh/demos/`. This module contains the recipe logic and nothing else: no CLI plumbing, no test assertions, no doc formatting.

```
src/openagentmesh/demos/
    __init__.py
    hello_world.py
    multi_agent.py
    shared_plan.py
    ...
```

### Three consumers, one source

| Consumer | How it uses the demo module |
|----------|----------------------------|
| **CLI** (`oam demo <name>`) | Spins up `AgentMesh.local()`, imports and runs the module's entry point |
| **Docs** (`docs/cookbook/`) | Embeds the module source via file include directives; no hand-maintained code blocks |
| **Tests** (`tests/cookbook/`) | Imports the module, layers assertions and fixtures on top |

### CLI surface

```
oam demo list                    # list available demos
oam demo run <name> [--json]     # run a demo against a local mesh
oam demo show <name>             # print the demo source code to stdout
```

`oam demo run` handles mesh lifecycle automatically: it starts a local NATS instance (via `AgentMesh.local()`), runs the demo, and tears down. No external setup required.

### Demo module contract

Each demo module must expose:

```python
"""One-line description shown by `oam demo list`."""

async def main(mesh: AgentMesh) -> None:
    """Entry point. The mesh is already connected."""
    ...
```

The `mesh` argument is injected by the CLI runner. The module must not manage its own mesh lifecycle. This keeps demos focused on the recipe logic and makes them trivially testable.

### Pipeline update

The Documentation Driven Development pipeline becomes:

```
Brainstorm -> Shape -> ADR (with code sample) -> Test -> Implement -> Finalize demo + docs
```

The ADR still contains an illustrative code sample for design discussion. Once implemented, the demo module becomes the canonical version. Docs reference it via include; the ADR sample is historical context.

### Doc includes

Docs use fenced code blocks with a file path reference that Zensical resolves at build time:

```markdown
```python title="hello_world.py"
--8<-- "src/openagentmesh/demos/hello_world.py"
```​
```

If a recipe needs annotation or partial inclusion, snippet markers (`# --8<-- [start:name]`) isolate the relevant section.

## Consequences

- **Positive:** One source of truth for user-facing code. Zero drift between docs, CLI, and tests. Users can run any recipe with a single command.
- **Positive:** Reduces total code surface. No more maintaining parallel code blocks in docs.
- **Positive:** Demo source is importable, so tests are thin wrappers with assertions.
- **Negative:** Demo modules have a dual constraint: they must read well as documentation AND run correctly as programs. Heavy setup or teardown logic must stay in the CLI runner, not the module.
- **Negative:** File-include directives create a build-time dependency; broken paths fail silently unless CI checks them.

## Mitigations

- CI job validates all doc includes resolve to existing files.
- Demo modules are kept short (under 80 lines). Complex recipes split into multiple modules or use helper imports from the same package.
