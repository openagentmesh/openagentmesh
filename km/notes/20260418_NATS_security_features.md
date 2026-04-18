# NATS Security Features: Research for OAM Authn/z Shaping

**Status:** research note, not a decision
**Related:** ADR-0033 (defers auth), ADR-0035 (asks how control plane overlaps with NATS accounts), `docs/architecture/subjects.md`
**Purpose:** catalog what NATS provides out of the box so the upcoming authn/z ADR can pick primitives instead of inventing them.

## 1. What NATS Gives Us

NATS ships six authentication modes and a first-class authorization model. Authorization is always per-subject.

| Mode | Secret model | Scale fit | Notes |
|------|--------------|-----------|-------|
| No auth | none | local dev only | Current OAM default (ADR-0033) |
| Token | shared string | small, trusted | Single token, no per-client identity |
| User + password | shared per user | small, trusted | Per-user identity, static config |
| NKeys | Ed25519 keypair | any | Strong identity, private key stays on client, no shared secret |
| NKey + JWT (decentralized) | keypair + signed claims | multi-tenant, large | Operator/Account/User hierarchy, servers verify cryptographically |
| mTLS | X.509 certs | service mesh | Identity from cert CN; can combine with other modes |

Combinations are allowed: mTLS for transport identity + JWT for account claims is the typical production stack.

### NKey key types

Four prefixes in the NATS-specific Ed25519 encoding:

| Prefix | Type | Role |
|--------|------|------|
| `O` | Operator | Signs account JWTs |
| `A` | Account | Signs user JWTs, owns subject namespace |
| `U` | User | Client identity |
| `S` | Server | Server identity |

The `nsc` CLI manages the full hierarchy. User credentials ship as a `.creds` file bundling the user JWT and NKey seed.

## 2. Authorization Model

Permissions are scoped to two verbs, `publish` and `subscribe`, each with `allow` and `deny` lists over subject patterns. Wildcards `*` (one token) and `>` (tail) work the same as in subscriptions.

```conf
permissions {
  publish   { allow: ["orders.>"]     deny: ["orders.admin.>"] }
  subscribe { allow: ["orders.>", "_INBOX.>"] deny: [">"] }
  response  { max: 1, expires: "1s" }  # reply window for request/reply
}
```

Two things to remember:

- Request/reply needs `_INBOX.>` on subscribe for the requester and allow-publish on the target subject.
- Deny-by-default (`deny: [">"]` then allowlist) is the recommended posture.

## 3. Accounts: Hard Multi-Tenancy

Accounts are full subject-namespace isolation. A subject in account A is invisible to account B unless explicitly exported/imported.

```conf
accounts {
  TEAM_A { users: [{ user: alice, password: pw }] }
  TEAM_B { users: [{ user: bob,   password: pw }] }
}
```

Selective sharing via `imports` / `exports` covers cross-account streaming or request/reply without merging namespaces.

Accounts are the **single most relevant NATS primitive** for OAM's multi-tenant story: tenants get isolation for free, no SDK code required.

## 4. JetStream and KV Permissions

Catalog, registry, results, and object store all live in JetStream. Permissions are enforced on the underlying subjects, not on the bucket API:

- KV bucket `X` puts/gets/watches use subjects under `$KV.X.>`.
- Object store bucket `Y` uses `$O.Y.>`.
- JetStream API (stream/consumer/KV/OS admin) uses `$JS.API.>`.

Granting an agent read-only access to the catalog means allowing `subscribe` on `$KV.mesh-catalog.>` and the relevant `$JS.API.*` admin subjects the client library calls during `watch`/`get`.

System events live under `$SYS.>` and typically require a dedicated system account.

## 5. TLS and mTLS

Transport security is orthogonal to application auth. Two useful modes:

- `verify: true` — client certs required, identity still comes from token/user/JWT.
- `verify_and_map: true` — derive username from the cert CN and look it up in `authorization.users`. Fully cert-based identity.

For a service-mesh-like deployment where every agent has a workload identity (SPIFFE, cloud workload identity), `verify_and_map` aligns neatly with the existing auth model.

## 6. Mapping to OAM Constructs

OAM has a well-defined subject layout (`docs/architecture/subjects.md`). Each subject class maps to a distinct permission pattern.

| OAM construct | Subject pattern | Natural permission grant |
|---------------|-----------------|-------------------------|
| Agent handler (server side) | `mesh.agent.{channel}.{name}` | subscribe + response |
| Agent invocation (client side) | `mesh.agent.{channel}.{name}` + `_INBOX.>` | publish + subscribe on inbox |
| Catalog read | `$KV.mesh-catalog.>` | subscribe |
| Registry read (contract fetch) | `$KV.mesh-registry.{channel}.{name}` | subscribe |
| Registration (write own contract) | `$KV.mesh-registry.{channel}.{name}` | publish on own key only |
| Health heartbeat | `mesh.health.{channel}.{name}` | publish |
| Health observation (control plane) | `mesh.health.>` | subscribe |
| Event emission | `mesh.agent.{channel}.{name}.events` | publish |
| Event subscription | `mesh.agent.{channel}.{name}.events` | subscribe |
| Async results | `mesh.results.{request_id}` | publish (callee) / subscribe (caller) |
| Errors / DLQ | `mesh.errors.{channel}.{name}` | publish (callee) / subscribe (operator) |

Key observation: **channels are subject prefixes**, so channel-scoped permissions are a native NATS concept. An agent registered in channel `finance.risk` naturally gets permissions scoped to `mesh.agent.finance.risk.>` with no OAM-specific enforcement layer.

## 7. Options on the Authn/z Design Axis

Three distinct levels of ambition, each viable:

### Option A: Lean on NATS, thin SDK surface

- SDK accepts a `.creds` file path or NKey seed in `AgentMesh(url=..., creds=...)`.
- OAM defines a recommended permission template per "role" (agent publisher, catalog observer, full mesh admin) as docs + an `oam` helper command that emits `nsc` scripts.
- Multi-tenancy = NATS accounts. One account per tenant. The control plane (ADR-0035) works inside an account; cross-tenant visibility is explicit account imports.
- Authz enforcement is 100% NATS. OAM adds no runtime checks.

Pros: zero protocol surface for auth, maps 1:1 with NATS operator experience, plays well with existing NATS deployments.
Cons: operators must learn `nsc`; no OAM-native concept of "agent identity" distinct from NATS user identity.

### Option B: OAM-native identity, NATS as enforcement

- OAM defines `AgentIdentity` (name + signing key pair) as a first-class object.
- The `@mesh.agent` decorator binds to an identity; registration carries a signature.
- Behind the scenes OAM issues a NATS user JWT per identity, scoped to the agent's subjects.
- Control plane commands (ADR-0035) rotate JWTs, revoke identities, tighten permissions.

Pros: cleaner mental model for agent authors, keeps NATS details under the SDK, enables per-agent key rotation without NATS expertise.
Cons: significant surface. Need a key issuer service. Probably Phase 2+.

### Option C: Hybrid — transport identity from mTLS, application identity from OAM

- mTLS verifies the workload (fits Kubernetes, SPIFFE, cloud workload identity).
- OAM adds a thin claim layer on top of NATS user permissions for per-channel scopes.
- Accounts are reserved for tenant isolation.

Pros: aligns with existing service-mesh deployments.
Cons: depends on the operator's infra already providing workload identity. Less useful for the "laptop dev" persona.

## 8. Questions the ADR Must Answer

1. **Tenancy model.** Does "tenant" mean a NATS account, or an OAM-level concept layered on top of a single account? Accounts give hard isolation but complicate cross-tenant agent discovery.
2. **Identity granularity.** Per-agent identity, per-process, or per-human-operator? The answer shapes whether credentials rotate with agent lifecycle or with deployment.
3. **Key issuance.** Who signs user JWTs? A Phase-1-compatible answer is "the operator runs `nsc` out of band"; Phase 2 might introduce an issuer service.
4. **SDK surface.** What does `AgentMesh(url=..., auth=...)` look like? A credentials path? A callable? An object with pluggable providers?
5. **Control-plane overlap.** ADR-0035 defines channel scoping and kill switches. With NATS permissions, much of this is free — but only at registration/start time. Does OAM still need its own runtime scoping on top?
6. **"Hello World" preservation.** ADR-0008 (DX-first) commits to a sub-30-line Hello World. The auth story must keep local-dev frictionless (AgentMesh.local() stays unauthenticated) while giving production a clear path.
7. **BYOK for agent-internal secrets.** ADR-0023 explicitly punts BYOK for LLM credentials. The authn/z ADR should confirm this stays out of scope — it's about mesh access, not downstream API keys.

## 9. Recommended Phasing (Preliminary)

- **Phase 1 (current):** keep open mesh. Document a recommended NATS config for "put a password on it" so users aren't defenseless when they move off localhost.
- **Phase 2:** decentralized auth. Accept NATS `.creds` in `AgentMesh(...)`. Ship `oam auth init` that wraps `nsc` to produce operator/account/user hierarchies aligned with OAM subject patterns. Publish permission templates per role.
- **Phase 3:** OAM-native identity abstraction if the need materializes (multi-tenant hosted mesh, per-agent rotation, revocation on control-plane commands).

Defer anything that requires building an issuer service or custom token format until real use cases demand it. NATS JWT is a well-trodden path; riding it buys time.

## 10. References

- NATS docs: Security, Authentication, Authorization, JWT, Accounts sections.
- `nsc` CLI for JWT/NKey management.
- ADR-0033 (auth deferred), ADR-0035 (control plane overlap), ADR-0023 (BYOK out of scope).
- `docs/architecture/subjects.md` — the ground truth for subject-to-permission mapping.
