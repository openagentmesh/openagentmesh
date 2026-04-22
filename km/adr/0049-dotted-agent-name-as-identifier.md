# ADR-0049: Dotted agent name as sole identifier

- **Type:** api-design
- **Date:** 2026-04-22
- **Status:** spec
- **Amends:** ADR-0012 (contract schema), ADR-0020 (catalog vs NATS wildcards)
- **Source:** conversation (review of `_resolve_subject` channel-handling asymmetry)

## Context

Agents are currently identified by two fields: a `name` (leaf segment) and an optional `channel` (dotted prefix). These combine into the invocation subject `mesh.agent.{channel}.{name}`, error subject `mesh.errors.{channel}.{name}`, event subject `mesh.agent.{channel}.{name}.events`, and registry key `{channel}.{name}`.

The `docs/concepts/channels.md` page defines channels as "hierarchical namespace prefixes that group agents by domain or team" with "map[ping] directly to NATS subject hierarchy". The concept has no semantics beyond "a prefix path segment". NATS already models hierarchy natively through dotted subjects.

The split causes real problems:

1. **Subject computation is duplicated and divergent.** `_subjects.py` has three helpers that each take `(name, channel)` and concatenate. `_resolve_subject` in `_mesh.py` reimplements the no-channel form as a string literal for the remote fallback and drops the channel entirely. A channelled remote agent cannot be reached via `call`/`stream`/`send` today.
2. **`call`/`stream`/`send` have no `channel` parameter.** Only `subscribe` accepts one. Ambiguity if two agents share a name across channels is silently ignored.
3. **Two fields to marshal everywhere.** Every model, every JSON envelope, every decorator path, every test fixture carries both.

Since "channel" is purely a prefix convention, the split is accidental complexity.

## Decision

Fold `channel` into `name`. An agent's name is the full dotted identifier, identical to the subject tail after `mesh.agent.`. Drop the `channel` field from `AgentSpec`, `CatalogEntry`, and `AgentContract`.

### What changes

1. **`AgentSpec.name`** accepts a dotted identifier, e.g. `"finance.risk.scorer"` or `"echo"`. No `channel` field.
2. **`_subjects.py` helpers** become single-argument: `compute_subject(name)`, `compute_error_subject(name)`, `compute_registry_key(name)`. Trivial; may be inlined later.
3. **`_resolve_subject(name)`** returns `f"mesh.agent.{name}"`. No local/remote asymmetry, no fallback.
4. **`catalog(channel=X)`** stays. Semantics become "prefix filter": an agent matches if its name equals `X` or starts with `X + "."`. This is what users already expect.
5. **`subscribe(channel=X)`** stays. Continues to subscribe to `mesh.agent.{X}.>`, unchanged.
6. **Name validation.** A name is a non-empty sequence of dot-separated segments matching `[a-zA-Z0-9_-]+`. Reject leading or trailing dots, consecutive dots, and the empty string.

### What stays the same

- **Wire format.** Every subject, error subject, and event subject on NATS is byte-identical to the current scheme. `mesh.agent.finance.scorer` with `name="scorer", channel="finance"` matches `mesh.agent.finance.scorer` with `name="finance.scorer"`. This is an API refactor, not a protocol change.
- **Contract registry layout.** Registry key is still `finance.scorer`. `to_registry_json` retains the A2A top-level `name` field.
- **LLM tool conversion.** `_sanitize_name` already replaces `.` with `_` to satisfy tool-name regex; no change.
- **`x-agentmesh.channel`** is removed from the registry JSON. External consumers that need it can derive it: `name.rsplit(".", 1)[0] if "." in name else None`.

### Code sample

```python
from openagentmesh import AgentMesh, AgentSpec
from pydantic import BaseModel

class ScoreInput(BaseModel):
    profile: str

class ScoreOutput(BaseModel):
    score: float

mesh = AgentMesh()

# Dotted name encodes the channel hierarchy directly.
spec = AgentSpec(
    name="finance.risk.scorer",
    description="Scores credit risk from a company profile.",
)

@mesh.agent(spec)
async def scorer(req: ScoreInput) -> ScoreOutput:
    return ScoreOutput(score=0.42)

# Root-level agent: no dots.
root_spec = AgentSpec(name="echo", description="Echoes messages.")

@mesh.agent(root_spec)
async def echo(msg: str) -> str:
    return msg

# Invocation: always by full dotted name.
result = await mesh.call("finance.risk.scorer", {"profile": "..."})

# Discovery: filter by channel prefix.
finance_agents = await mesh.catalog(channel="finance")       # all under finance.*
risk_agents = await mesh.catalog(channel="finance.risk")     # exact tier
all_agents = await mesh.catalog()                            # everything

# Event subscription: unchanged.
async for event in mesh.subscribe(channel="finance"):
    process(event)
```

### Migration notes

No users exist. All demo code, tests, and docs are rewritten in this change. No backward compatibility shim is provided.

## Consequences

- `_models.py`: Remove `channel` from three models. Add name validator (regex + non-empty + segment shape). Update `to_catalog_entry` and `to_registry_json`.
- `_subjects.py`: Collapse to single-arg helpers.
- `_mesh.py`: Simplify `_resolve_subject`, `_resolve_event_subject`, `_emit_publisher_events`, agent registration, shutdown registry cleanup.
- `_discovery.py`: Change `catalog` filter to prefix match, drop `channel` param from `contract` and `discover`.
- `_invocation.py`: `subscribe(channel=X)` still yields `mesh.agent.{X}.>`; drop channel override in `_resolve_event_subject`.
- Demos: Rewrite five demos with dotted names.
- Tests: Mechanical rename. Assertions on `entry.channel` become assertions on `entry.name` prefix.
- Docs: Rewrite `docs/concepts/channels.md` to present channels as a *naming convention*, not an API field. Update `docs/api/*` and cookbook samples.

## Alternatives Considered

**Fix `_resolve_subject` in place, keep the split.** Patches one symptom. Every future code path that derives a subject still has to carry both fields and risks the same class of bug. Does not address the conceptual redundancy.

**Add `channel` param to `call`/`stream`/`send`.** Plugs the remote invocation gap but makes the API wider, not narrower. The underlying duplication remains.

**Keep `channel` as a derived property on the models** (read-only, computed from `name`). Considered and rejected: adds a second way to refer to the same information and invites callers to build logic on the split representation again. Users who need the prefix can compute it themselves in one line.
