# ADR-0061: TypeScript client SDK (`@openagentmesh/sdk`, consume-only, isomorphic)

- **Type:** api-design / new-surface
- **Date:** 2026-05-31
- **Status:** spec
- **Source:** Direct request to build the TypeScript SDK. Prior art: ADR-0056 (admin UI) locked `@nats-io/{nats-core,jetstream,kv}@3.x` + `wsconnect` as the browser mesh transport; the wildfire UI (`ui/src/lib/{nats,catalog,fleet,events}.ts`) proved the client-side patterns against live NATS. `km/specs/wildfire/sdk-desiderata.md` lists the affordances browser clients need (instance_id, public publish, KV ergonomics).
- **Mirrors:** the Python SDK wire protocol (`src/openagentmesh/`): ADR-0005 (streaming), ADR-0012/0049 (subjects + dotted names), ADR-0025/0060 (KV), ADR-0047 (pre-flight mismatch), ADR-0057 (errors), ADR-0058 (publish), ADR-0059 (instance_id).
- **Note:** The project `CLAUDE.md` lists "TypeScript SDK" as out of the original Phase 1 scope. This ADR promotes a **consume-only** first slice ahead of the full SDK: it is the minimum surface the admin UI and demo dashboards already need, and it is bounded (no agent hosting). Agent hosting in TS is explicitly deferred.

## Context

OAM today ships one SDK (Python). Every browser-facing surface (admin UI per ADR-0056, wildfire dashboard) currently re-implements ad-hoc NATS client glue (`ui/src/lib/`): open a `wsconnect`, watch the `mesh-catalog` KV key, mirror fleet presence, subscribe to event subjects. That glue is the TypeScript SDK in embryo, copy-pasted per app and untyped against the protocol.

A first-class TS SDK consolidates that glue into a typed, tested package that speaks the OAM wire protocol faithfully. The wire protocol is fully specified by the Python implementation; a parallel protocol-map pass verified every literal subject, header, KV bucket/key, and error code against source (see the Wire Conformance appendix).

**Scope of this slice (consume-only).** The TS client *consumes* a mesh: it invokes agents (`call`/`stream`/`send`), publishes to subjects (`publish`), subscribes to events (`subscribe`), runs discovery (`catalog`/`contract`/`discover`), and reads/watches shared-context KV (`mesh.kv`). It does **not** register agents, run handlers, infer handler shapes, or serve queue groups. Those (the "full mirror") are a later ADR.

**Runtime.** Isomorphic. The `@nats-io` v3 ecosystem cleanly separates connection logic from transport, so one codebase serves both:
- **Browser:** `wsconnect` from `@nats-io/nats-core` over a NATS WebSocket listener (the ADR-0056 path).
- **Node:** `@nats-io/transport-node` TCP connect (the path the embedded `nats-server -js` exposes; the Python `local()` server is TCP-only).

`AgentMesh.connect()` selects the transport from the server URL scheme (`ws://`/`wss://` → `wsconnect`; `nats://`/`tls://` → node TCP). Core verb logic operates on a `NatsConnection` and is transport-agnostic.

## Decision

Ship `@openagentmesh/sdk`: a TypeScript package exporting an `AgentMesh` class plus the typed error hierarchy and data shapes. Class name stays `AgentMesh` to mirror the Python ergonomics (`import { AgentMesh } from "@openagentmesh/sdk"`).

### Package & layout

- npm name `@openagentmesh/sdk`; lives at `sdk-ts/` in the repo root (sibling to the Python `src/`). pnpm workspace-ready, self-contained for now.
- Tooling: pnpm, TypeScript strict (target ES2022, `lib` ES2022 + DOM), ESM output, **Vitest** as the test runner (matches the repo's Vite/`@nats-io` v3 ESM ecosystem).
- Deps: `@nats-io/nats-core@^3`, `@nats-io/jetstream@^3`, `@nats-io/kv@^3`. Node tests also use `@nats-io/transport-node@^3`. No runtime dependency on Zod (see validation below).

### Public surface

```ts
class AgentMesh {
  static connect(opts: ConnectOptions): Promise<AgentMesh>
  readonly instanceId: string

  call(name: string, payload?: unknown, opts?: { timeout?: number }): Promise<Record<string, unknown>>
  stream(name: string, payload?: unknown, opts?: { timeout?: number; signal?: AbortSignal }): AsyncIterable<Record<string, unknown>>
  send(name: string, payload?: unknown, opts?: SendOptions): Promise<void>
  publish(subject: string, payload: unknown | Uint8Array | string, opts?: { headers?: Record<string,string> }): Promise<void>
  subscribe(opts: { agent?: string; channel?: string; subject?: string; timeout?: number; signal?: AbortSignal }): AsyncIterable<Record<string, unknown>>

  catalog(opts?: { channel?: string; tags?: string[]; streaming?: boolean; invocable?: boolean }): Promise<CatalogEntry[]>
  contract(name: string): Promise<AgentContract>
  discover(opts?: { channel?: string }): Promise<AgentContract[]>

  readonly kv: KVStore   // mesh-context bucket
  close(): Promise<void>
}
```

### Wire mapping (verified literals — see appendix for citations)

- **Subjects:** invocation `mesh.agent.{name}`; events `mesh.agent.{name}.events`; channel subscribe `mesh.agent.{channel}.>`; stream chunks `mesh.stream.{requestId}`; managed reply `mesh.results.{requestId}`. `{requestId}` is a uuid4 **hex** (32 lowercase hex chars). No `oam.*` aliasing exists in the message layer (the stray `oam.catalog.>` comment in `catalog.ts` is dead — discovery is KV-watch, not a subject mirror).
- **Headers** (all string→string): outbound `X-Mesh-Request-Id`, `X-Mesh-Stream: "true"` (stream only), `X-Mesh-Reply-To` (send manual-reply only), `X-Mesh-Instance-Id` (auto-stamped on every outbound msg via setdefault — user headers win), `X-Mesh-Content-Type` (publish only). Inbound `X-Mesh-Status` (`"ok"`/`"error"`; absence ⇒ success), `X-Mesh-Source`, plus stream framing `X-Mesh-Stream-Seq` (0-indexed int-as-string) and `X-Mesh-Stream-End` (`"true"`/`"false"`).
- **Payloads:** JSON convention = UTF-8 of `JSON.stringify`. Empty/`null` request body ⇒ empty bytes. Empty response body ⇒ `{}`. `publish` content types: object⇒`application/json`, `Uint8Array`⇒`application/octet-stream`, string⇒`text/plain`.
- **Discovery KV:** catalog = bucket `mesh-catalog`, **single key `catalog`**, value = JSON array of `CatalogEntry`. Registry = bucket `mesh-registry`, key = agent name (verbatim dotted id), value = A2A-shaped JSON with OAM fields under `x-agentmesh`. `input/output` schemas live under `skills[0].inputSchema`/`outputSchema`.
- **Shared KV:** bucket `mesh-context`.
- **Errors:** JSON body `{ code, message, agent, request_id, details }` with `X-Mesh-Status: error`. Codes → classes: `invalid_input`→InvalidInput, `handler_error`→HandlerError, `invocation_mismatch`→InvocationMismatch, `not_found`→NotFound, `timeout`→MeshTimeout, `connection_failed`→ConnectionFailed, `chunk_sequence_error`→ChunkSequenceError, `kv_key_exists`→KVKeyExists. Unknown code ⇒ base `MeshError` with `code` preserved (forward-compat).

### Resolved design decisions (divergences from Python, made explicit)

1. **Timeouts are milliseconds** (idiomatic JS), not Python's float-seconds. Defaults: `call` 30_000, `stream` 60_000, `send` 60_000, `subscribe` none. Documented prominently to avoid 1000× porting bugs.
2. **Schema validation is opt-in and Zod-free at the core.** `kv.getModel(key, schema)` / `putModel` / `getModelList` accept any structural validator `{ parse(x): T }` (Zod-compatible, but also a hand-written guard). The invocation verbs return plain `Record<string, unknown>`; callers validate. No hard Zod dependency.
3. **`AgentContract` surfaces `inputSchema`/`outputSchema`** extracted from `skills[0]` — improving on the current Python `contract()`, which leaves them `None`. Documented as an intentional improvement, not a wire change.
4. **KV exposes two watch flavors:** `watch(key)` yields decoded **string values on PUT** (mirrors Python `kv.watch`); `watchEntries(prefix, cb)` yields full entries incl. deletes (the fleet-mirror need). The TS `operation` enum is normalized to `"PUT" | "DELETE"` (collapsing `@nats-io/kv`'s `DEL`/`PURGE` → `DELETE`).
5. **`send()` managed-callback** returns `Promise<void>`; the reply subscription drains in the background and auto-stops on the terminal message or timeout, routing failures to `onError`. No unhandled-rejection leak.
6. **`stream()` cancellation** via optional `AbortSignal` and/or breaking the `for await`; the stream subscription is always torn down in a `finally`. The client subscribes to `mesh.stream.{requestId}` **before** publishing the request (race-critical).
7. **Pre-flight capability check (ADR-0047)** is best-effort: consults the catalog cache; if the target agent is known, a wrong-verb call throws `InvocationMismatch` locally; if unknown/absent, the request goes out and the agent answers. `connect()` eagerly seeds the catalog cache (`kv.get("catalog")`) and starts a watcher.

### Code sample (DX contract)

```ts
import { AgentMesh, MeshError, MeshTimeout, NotFound, InvocationMismatch } from "@openagentmesh/sdk";

// Connect (browser ws or node tcp — scheme picks the transport)
const mesh = await AgentMesh.connect({ servers: "nats://127.0.0.1:4222" });
mesh.instanceId; // stable uuid hex, stamped on every outbound message

// call — request/reply
const score = await mesh.call("finance.risk.scorer", { applicant: "A-1023" });

// stream — async iterable of chunks
for await (const chunk of mesh.stream("nlp.summarizer", { url })) render(chunk);

// send — fire-and-forget, or managed reply
await mesh.send("audit.logger", { event: "login" });
await mesh.send("billing.charge", { amount: 100 }, {
  onReply: (m) => ack(m),
  onError: (e: MeshError) => warn(e.code, e.message),
});

// publish — arbitrary subject (object→json, Uint8Array→octet-stream, string→text)
await mesh.publish("telemetry.uav.42", { x: 10, y: 4 });

// subscribe — by agent | channel | subject (exactly one)
for await (const evt of mesh.subscribe({ channel: "wildfire.fleet" })) update(evt);

// discovery — catalog (cheap) → contract (full)
const agents = await mesh.catalog({ channel: "finance", streaming: true });
const contract = await mesh.contract("finance.risk.scorer"); // throws NotFound

// shared-context KV (mesh-context bucket)
const grid = await mesh.kv.get("wildfire.fire.state");
for await (const v of mesh.kv.watch("wildfire.fire.state")) applyFire(v);
const stop = mesh.kv.watchEntries("wildfire.fleet.>", (e) =>
  e.operation === "PUT" && e.value ? upsert(e.key, JSON.parse(e.value)) : remove(e.key),
);

// typed errors mirror the wire envelope
try {
  await mesh.call("some.publisher", {});
} catch (err) {
  if (err instanceof InvocationMismatch) {/* wrong verb (pre-flight) */}
  else if (err instanceof MeshTimeout) {/* err.subject, err.timeout */}
  else if (err instanceof NotFound) {/* err.agent */}
  else if (err instanceof MeshError) {/* err.code, err.message, err.requestId, err.details */}
}

await mesh.close();
```

### Test strategy (TDD)

Vitest against a real `nats-server -js` (the binary already at `~/.agentmesh/bin/nats-server`), spawned per suite over TCP via `@nats-io/transport-node`. Because this is a *client* SDK, tests pair the client with a **wire-level agent simulator** (a test helper that subscribes to `mesh.agent.{name}`, replies with the correct headers/body, emits stream chunks, publishes events, and seeds the `mesh-catalog` / `mesh-registry` / `mesh-context` KV buckets). This keeps tests self-contained in TS (no Python runtime) while exercising the real protocol over real NATS. Red → green → refactor per verb wave.

## Consequences

- New top-level `sdk-ts/` package; the repo becomes polyglot. CI later needs a pnpm + nats-server job (out of scope here; no CI gate today per the solo workflow).
- The wildfire UI `ui/src/lib/` glue is superseded by this package; migrating the dashboard onto `@openagentmesh/sdk` is a follow-up, not part of this slice.
- Divergences (ms timeouts, surfaced schemas, two watch flavors) are documented; a future "full mirror" ADR (agent hosting in TS) inherits this wire layer unchanged.
- Docs: a `docs/` TypeScript quickstart + cookbook recipes mirror the Python ones once green.

## Alternatives Considered

**Browser-only client (extend `ui/src/lib/`).** Rejected: Node + Vitest is the only sane TDD path (no headless-browser NATS WS harness needed), and Node support is free given the `@nats-io` v3 transport split. Browser stays a first-class target via `wsconnect`.

**Full mirror (agent hosting) in this slice.** Rejected: hosting needs handler-shape inference, queue-group serve, contract publish, and a CAS catalog writer — a much larger port with its own design questions. Consume-only is the bounded, immediately-useful first cut.

**Hard Zod dependency for validation.** Rejected: forces a dep and an opinion on every consumer. Structural `{ parse }` validators keep the core schema-agnostic while staying Zod-compatible.

**Seconds for timeouts (faithful to Python).** Rejected: non-idiomatic in JS; ms is the ecosystem norm. The divergence is documented to protect cookbook ports.
