# ADR-0050: Docstring as fallback for `AgentSpec.description`

- **Type:** api-design
- **Date:** 2026-04-24
- **Status:** discussion
- **Source:** conversation (idiomatic Python convention vs. explicit protocol field)

## Context

`AgentSpec` (ADR-0030) carries a required `description` string that is registered in the catalog and consumed by LLMs for tool selection (see ADR-0039 on contract-to-tool conversion). Today it is supplied explicitly as a keyword argument:

```python
spec = AgentSpec(
    name="summarizer",
    description="Summarize text to bullet points. Use for long documents. Not for code.",
)

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...
```

Idiomatic Python frameworks pull the same semantic content from the function's docstring:

- **FastAPI** uses the docstring as the OpenAPI operation description.
- **Pydantic** promotes class docstrings to JSON Schema `description`.
- **LangChain** takes the tool docstring as the LLM-visible tool description.
- **Typer / Click** use docstrings for CLI help text.

Developers reaching for OAM will expect the same pattern. Writing a description twice (once in the spec, once in the docstring for IDE hover) is duplication.

Two tensions complicate a simple "use the docstring" rule:

1. **Contract vs. code doc.** `description` is a wire contract: it lands in the registry and is consumed by remote LLMs for tool selection. Docstrings are historically authored for human readers of source. The same text can serve both, but not all docstrings are shaped for LLM selection (rambling prose, Args/Returns sections, implementation notes).

2. **Two sources of truth.** If both the explicit field and the docstring are set and they diverge, which one ships? Silent precedence invites surprises.

## Decision

Make `description` optional on `AgentSpec`. Resolve it at decoration time with this precedence:

1. Explicit `description` on `AgentSpec` -> use it.
2. Otherwise, the handler's `__doc__` (dedented via `inspect.cleandoc`) -> use it.
3. Otherwise, raise `AgentSpecError` at decoration time: "agent '<name>' has no description. Set `AgentSpec.description` or add a docstring to the handler."

The decorator, not the model, performs resolution. `AgentSpec` remains a pure data model; the handler is not visible to it.

### Code sample (DX contract)

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

@mesh.agent(AgentSpec(name="summarizer"))
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    """Summarize text to 3 bullet points. Use for long documents. Not for code."""
    return SummarizeOutput(bullets=await call_llm(req.text))
```

Equivalent to:

```python
spec = AgentSpec(
    name="summarizer",
    description="Summarize text to 3 bullet points. Use for long documents. Not for code.",
)

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    return SummarizeOutput(bullets=await call_llm(req.text))
```

### Full docstring, not first line only

The full docstring is used, after `inspect.cleandoc()` dedents and strips it. Rationale:

- FastAPI and LangChain both use the full docstring.
- Summary-first-line conventions (PEP 257) make the whole docstring useful when LLMs select the agent: first line is the hook, remaining lines are disambiguating detail.
- A first-line-only rule invents a new convention developers must learn.

Developers who want a terse registry entry write a one-line docstring. Developers who want a detailed one write a longer docstring. Both work without special rules.

### Divergence between explicit field and docstring

If both are set and they differ, explicit wins. The SDK emits a `logging.WARNING` once per handler at registration time:

```
AgentSpec.description for 'summarizer' differs from handler docstring. Using explicit value.
```

Rationale: the two can legitimately diverge (docstring documents the Python function for IDE hover; `description` is the wire contract with LLM-selection framing). But divergence is usually accidental. A warning surfaces the inconsistency without forcing resolution.

### Args/Returns sections in docstrings

No special handling. If the developer writes a Google- or NumPy-style docstring with `Args:` and `Returns:` blocks, the full text ships to the registry. The argument and return schemas already travel as JSON Schema via handler type hints (ADR-0031); the docstring prose is registered verbatim.

Stripping structured sections is tempting but adds a parser dependency and a new edge case surface (multiple formats, ambiguous section markers). Developers who care about registry cleanliness write compact docstrings.

### `AgentSpec` schema change

```python
class AgentSpec(BaseModel):
    name: str
    description: str | None = None   # was: required
    channel: str | None = None
    tags: list[str] = []
    version: str = "0.1.0"
```

The `description` field becomes optional on the model. Resolution-or-raise happens in the decorator.

### `mesh.contract()` output

The resolved description (explicit or docstring) is what `mesh.contract(name)` returns and what appears in the registered catalog entry. Consumers see one field; they do not know or care which source it came from.

## Consequences

- `AgentSpec.description` becomes optional.
- `@mesh.agent` reads `handler.__doc__`, applies `inspect.cleandoc`, and populates the resolved description before registration.
- A handler with neither explicit description nor docstring fails at decoration time with a clear error. This surfaces the missing field early, not at catalog-read time.
- Divergence between explicit and docstring logs a warning; explicit wins.
- Cookbook and quickstart pages gain a recipe showing the docstring pattern (likely the dominant form once available).
- `docs/api/agentmesh.md` and `docs/concepts/contracts.md` document the resolution order explicitly.
- No wire-format change. The registry stores a single resolved `description` string as today.

## Alternatives Considered

**Docstring-only (drop explicit field).** Maximally idiomatic but loses a precise override for cases where docstring shape is wrong for LLM selection (heavy Args/Returns noise, implementation notes, multi-audience prose). Rejected: some agents genuinely need both a human-oriented docstring and an LLM-oriented registry description.

**Explicit-only (status quo).** Simple, one source of truth. Rejected: forces duplication with docstrings that developers will write anyway, and violates the Python norm users will bring from FastAPI/Pydantic/LangChain.

**First line of docstring only.** Matches PEP 257 summary convention and forces brevity. Rejected: diverges from FastAPI/LangChain behavior, invents a rule users must learn, and silently drops detail that helps LLM selection.

**Strip Args/Returns sections.** Cleans up Google/NumPy docstrings before registering. Rejected: adds a parser dependency, handles only some docstring styles, and creates an edge-case surface (malformed sections, ambiguous markers). Users who care write terse docstrings.

**Error on divergence between explicit and docstring.** Makes inconsistency a hard failure. Rejected: legitimate divergence exists (IDE hover vs. wire contract), and a hard failure breaks development flow for a minor issue. A warning is the right register.

**Warn if no explicit description is set.** Nudges users toward the explicit field even when docstring resolution succeeds. Rejected: defeats the point of the fallback; the docstring path should be first-class, not tolerated.
