# ADR-0037: OAM scope — per-agent visibility and reachability

- **Type:** api-design
- **Date:** 2026-04-18
- **Status:** spec
- **Related:** ADR-0035 (control plane), ADR-0030 (AgentSpec), ADR-0028 (CatalogEntry), ADR-0032 (catalog subscription), ADR-0038 (NATS authentication, pending)
- **Source:** conversation (shaping session on authn/z)

## Context

OpenAgentMesh currently assumes an open mesh: once an agent registers, every other agent can see it and invoke it. This is correct for the laptop-dev persona but too permissive once multiple teams, workflows, or untrusted agents share a mesh.

The authn/z shaping session identified two distinct concerns that a naive single-layer design would conflate:

1. **Trust boundary** — who is this NATS client, what credentials did they present, what subjects may they touch? This is a per-connection property, enforced cryptographically by NATS. It is covered in ADR-0038 (pending).

2. **Logical scoping** — inside a trusted process that may host several agents, which agents can see which, which agents can call which, and who may call back into which? This is a per-agent property that NATS cannot enforce because a single NATS connection is shared by every agent in the process.

Attempting to enforce per-agent policy at the NATS layer would force one process per agent, exploding credentials and deployment complexity with no corresponding security gain. Accepting the process as the NATS trust boundary and adding a separate, SDK-enforced **scope** layer on top is the honest model.

Scope is also the mechanism that lets Phase 1 ship useful multi-agent isolation behavior without any credential management at all. Developers experiment with visibility and reachability rules on an open mesh; later, when production auth arrives (ADR-0038), scope composes with it unchanged.

## Decision

Introduce **scope**, a per-agent declarative policy enforced entirely on the caller side by the SDK. Scope is orthogonal to and composes with NATS authentication.

### 1. Two-layer model

| Layer | Granularity | Enforcement | Purpose | Availability |
|-------|-------------|-------------|---------|--------------|
| NATS auth (ADR-0038) | per-process | cryptographic, server-side | trust boundary, credential identity | Phase 2+ |
| OAM scope (this ADR) | per-agent | cooperative, SDK-side | visibility and reachability | Phase 1 |

**Explicit non-claim: scope is not a security boundary.** An agent that bypasses the SDK and publishes directly to NATS will not be stopped by scope. The NATS layer is what contains an adversarial caller; scope is what shapes honest callers into the intended interaction topology. Documentation must say this in plain language.

### 2. Three scope fields

Scope is declared on the agent via `AgentSpec.scope` and consists of three orthogonal predicates:

| Field | Predicate | Source of truth |
|-------|-----------|-----------------|
| `can_call` | which agents may this agent invoke | caller's own spec |
| `can_see` | which agents appear in this agent's `catalog()` / `discover()` results | caller's own spec |
| `can_receive_from` | which callers may invoke this agent | target's contract (read by caller) |

All three use **channel-pattern vocabulary**: the same `*` / `>` wildcards that NATS subjects use. A bare agent name is the most specific pattern; a channel prefix is a coarser one.

```
"data.fetcher"     # exactly this agent
"data.*"           # any agent one level under data/
"finance.>"        # any agent at any depth under finance/
"*"                # any agent (equivalent to unrestricted)
```

Channel patterns subsume agent names (a full-path agent identifier is a channel with no wildcard), so one vocabulary serves both.

### 3. Caller-side enforcement, three checks

All three checks run on the caller, never on the receiver. The receiver SDK does no scope enforcement.

| Order | Check | What fires it |
|-------|-------|---------------|
| 1 | `can_call` (caller's own) | every `mesh.call()` / `mesh.stream()` / `mesh.send()` before any network I/O |
| 2 | `can_receive_from` (target's contract) | same call path, after contract fetch, before publish |
| 3 | `can_see` (caller's own) | applied as filter on `mesh.catalog()` / `mesh.discover()` results |

Check 1 is a purely local lookup. Check 2 requires the caller to have fetched the target's contract; since contracts are already fetched (or watched via ADR-0032) for invocation, no extra roundtrip is introduced. Check 3 is a post-processing filter on catalog reads.

On failure, the SDK raises `MeshError` with code `scope_denied`, a typed error carrying the field that denied the operation (`can_call` | `can_receive_from` | `can_see`) and the caller/target identifiers involved.

### 4. Default posture

| Posture | Semantics | When to use |
|---------|-----------|-------------|
| `allow` (default) | empty scope = everything allowed; only declared denies restrict | laptop dev, demos, single-team meshes |
| `deny` | empty scope = nothing allowed; only declared allows permit | shared meshes, cautious prod |
| `warn` | like `allow` at runtime, but logs every denial that would have fired under `deny` | migration: roll out scope gradually |

Posture is configured on the mesh instance:

```python
AgentMesh(scope_default="allow" | "deny" | "warn")
```

A literal rather than a boolean leaves room for `warn` now and other modes later. `allow` is the Phase 1 default so that Hello-World stays unchanged (ADR-0008 DX-first).

### 5. `AgentSpec` extension

`AgentSpec` (ADR-0030) gains a `scope` field, itself a Pydantic model:

```python
class AgentScope(BaseModel):
    can_call: list[str] = []
    can_see: list[str] = []
    can_receive_from: list[str] = []

class AgentSpec(BaseModel):
    name: str
    description: str
    channel: str | None = None
    tags: list[str] = []
    version: str = "0.1.0"
    scope: AgentScope | None = None
```

Absent `scope` means "use the mesh's `scope_default`". A partial scope (e.g., only `can_call` set) combines with the default for the unset fields.

### 6. Contract projection

`can_receive_from` must be readable by callers; it travels in the agent's contract stored in the registry. `can_call` and `can_see` are caller-local and **not** projected into the contract — they describe what the caller does, not what other agents should know about the caller.

In the contract schema (ADR-0012, A2A-compatible with namespace):

```yaml
x-agentmesh:
  scope:
    can_receive_from: ["orchestrator.*", "data.fetcher"]
```

## Code sample (DX contract)

```python
from openagentmesh import AgentMesh, AgentSpec, AgentScope

mesh = AgentMesh(scope_default="allow")

# A data fetcher that only accepts calls from data-plane agents
fetcher_spec = AgentSpec(
    name="fetcher",
    channel="data",
    description="Fetches normalized records from upstream sources.",
    scope=AgentScope(
        can_receive_from=["data.*", "orchestrator.*"],
    ),
)

@mesh.agent(fetcher_spec)
async def fetcher(req: FetchRequest) -> FetchResult:
    ...


# An orchestrator that may only call data-plane agents
# and only sees data-plane agents in its catalog
orchestrator_spec = AgentSpec(
    name="pipeline",
    channel="orchestrator",
    description="Coordinates a multi-step data pipeline.",
    scope=AgentScope(
        can_call=["data.*"],
        can_see=["data.*"],
    ),
)

@mesh.agent(orchestrator_spec)
async def pipeline(req: PipelineRequest) -> PipelineResult:
    # mesh.call enforces both can_call (self) and can_receive_from (target)
    records = await mesh.call("data.fetcher", FetchRequest(...))
    # mesh.catalog is filtered by can_see
    available = await mesh.catalog()      # only data.* agents appear
    return PipelineResult(...)


# A reporter with deny-default posture
reporter_mesh = AgentMesh(scope_default="deny")

reporter_spec = AgentSpec(
    name="weekly",
    channel="reports",
    description="Generates the weekly ops report.",
    scope=AgentScope(
        can_call=[],                      # cannot call anyone
        can_see=["data.*", "logging.*"],  # can read the catalog of these
    ),
)

@reporter_mesh.agent(reporter_spec)
async def weekly_report() -> Report:
    ...
```

## Staleness window (honest caveat)

`can_receive_from` lives in the target's contract. A caller reads it from its local cache or the registry. If the target changes its `can_receive_from` at runtime, there is a brief window (bounded by ADR-0032 catalog-change propagation, in the millisecond range) during which a caller may still publish on stale policy.

This is acceptable because scope is not a security boundary. The NATS layer (ADR-0038) is where revocation has strict semantics. Document this and move on.

## Envelope

No envelope changes are required for scope. Caller identity is not needed on the wire because the receiver performs no scope check. If a future ADR introduces an envelope `caller` field for observability or tracing, it is independent of this one.

## Relationship to ADR-0035 (control plane)

ADR-0035 proposes a control plane for runtime visibility and reachability changes (pause, disable, channel gates). This ADR supplies the **mechanism** that such a control plane would manipulate:

- Runtime scope changes push new contracts (for `can_receive_from`) or update a live mesh instance's declared scope (for `can_call` / `can_see`).
- ADR-0035's `paused` / `disabled` states can be implemented as forced `can_receive_from: []` at the control plane layer.
- Channel gates become control-plane-owned scope overrides injected into callers' resolution path.

ADR-0035's open question "should scoping be enforced at the SDK level, the NATS level, or both?" is answered: **both, at different granularities, for different purposes.** NATS enforces the trust boundary. OAM scope enforces the logical topology inside it.

## Non-goals

- **Security against adversarial code in-process.** Already covered; scope is cooperative.
- **Cryptographic caller attestation.** No envelope signing, no per-call identity proofs. Phase 2 (ADR-0038) provides a NATS-authenticated user identity when auth is on, which the SDK may surface later but does not consume for scope enforcement.
- **Quotas, rate limits, circuit breakers.** Scope is about allow/deny, not about throttling.
- **Cross-mesh federation rules.** Scope applies within a single mesh. A2A federation will need its own story.
- **External scope declaration (YAML, env).** For now, scope lives only on the decorator via `AgentSpec.scope`. External sources are a possible future extension.

## Consequences

- `AgentSpec` gains a `scope: AgentScope | None` field (ADR-0030 update).
- `AgentMesh` constructor gains `scope_default: Literal["allow", "deny", "warn"] = "allow"`.
- The contract schema (ADR-0012) gains `x-agentmesh.scope.can_receive_from`.
- `mesh.catalog()` / `mesh.discover()` apply `can_see` as a final filter. Callers see an already-filtered list; there is no way to inspect "what was filtered out".
- `MeshError` gains a `scope_denied` error code with structured metadata identifying the field and principals involved.
- Documentation must state, prominently, that scope is not a security boundary and must not be used for adversarial isolation.
- Phase 1 ships with scope available and `scope_default="allow"`. Hello-World is unchanged. Isolation demos gain a first-class vocabulary.
- ADR-0035 can reference this ADR as the runtime mechanism for its operator-facing commands.

## Alternatives Considered

**Receiver-side enforcement of `can_receive_from` via an envelope `caller` field.** Considered and rejected. Would require an envelope field, a receiver-side policy check on every invocation, and a spoof-detection story that scope explicitly does not provide. Caller-side enforcement is equivalent in behavior for honest SDKs (and no enforcement model can constrain dishonest ones without NATS-level credentials).

**NATS-only scoping via per-agent accounts or per-agent NATS users.** Rejected. Forces one NATS connection per agent, creating credential explosion and deployment drag for a property (logical topology) that does not need cryptographic enforcement. NATS accounts remain the right tool for tenant isolation, not agent isolation within a tenant.

**Scope declared in external config (YAML, env) instead of the decorator.** Deferred. Decorator-primary keeps scope co-located with the agent's intent and portable across deployments. External declaration is a future extension if operator workflows demand it.

**Single-field scope (allowlist of subjects, mirroring NATS permissions).** Rejected as too low-level. Agent authors reason about agents and channels, not subject patterns. Pushing NATS subject syntax into user code leaks an implementation detail that OAM has otherwise successfully hidden.

## Open Questions

- **Wildcard depth semantics in scope patterns.** NATS wildcards (`*` = one token, `>` = tail) are well-defined for subjects. Scope patterns reuse them on channel paths. Edge case: a bare agent name with a dot in it — is `"data.fetcher"` an agent in channel `data`, or a channel named `data.fetcher`? The SDK already resolves this ambiguity elsewhere (ADR-0020 distinguishes catalog filtering from NATS wildcards); scope uses the same rules. Confirmation test during the test phase.
- **Scope-default override at spec level.** Should an individual `AgentSpec` be able to override `scope_default` for itself? Leaving out for now; if `scope` is present and partial, unset fields fall back to the mesh default.
- **Composition with control plane (ADR-0035).** When ADR-0035 materializes, runtime scope updates must not silently conflict with spec-declared scope. Expected resolution: control-plane overrides win and are visible via a separate `mesh.control.effective_scope("agent-name")` inspection. Out of scope for this ADR.
