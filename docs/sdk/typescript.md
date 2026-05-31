# TypeScript Client

`@openagentmesh/sdk` is the TypeScript client for OpenAgentMesh. It is **isomorphic** (runs in the browser and in Node) and **consume-only**: it invokes and observes agents on a mesh but does not host them. It speaks the same wire protocol as the Python SDK over the [`@nats-io`](https://github.com/nats-io/nats.js) v3 client.

Use it to build dashboards, browser front-ends, and Node services that call agents, stream responses, publish events, run discovery, and read shared state, without standing up a Python process.

## Install

```sh
pnpm add @openagentmesh/sdk @nats-io/nats-core @nats-io/jetstream @nats-io/kv
```

In Node you also need the TCP transport:

```sh
pnpm add @nats-io/transport-node
```

## Connect

The server URL scheme selects the transport: `ws://` / `wss://` use the WebSocket transport (browser), `nats://` / `tls://` use the Node TCP transport.

```ts
import { AgentMesh } from "@openagentmesh/sdk";

const mesh = await AgentMesh.connect({ servers: "nats://127.0.0.1:4222" });
```

!!! tip "Browser bootstrap"
    Pass `{ configUrl: "/config.json" }` instead of `servers` to fetch the WebSocket URL from a `{ "nats_ws_url": "ws://..." }` document served by your app, the same convention the admin UI uses.

Every connection has a stable `mesh.instanceId` (a uuid hex), auto-stamped as the `X-Mesh-Instance-Id` header on every outbound message so receivers can attribute traffic to a specific replica.

## Invoke an agent

=== "call (request/reply)"

    ```ts
    const score = await mesh.call("finance.risk.scorer", { applicant: "A-1023" });
    // → { score: 0.9 }   (throws a typed error on an error reply or timeout)
    ```

=== "stream (async iterable)"

    ```ts
    for await (const chunk of mesh.stream("nlp.summarizer", { url })) {
      render(chunk);
    }
    // ends on the stream's end marker; throws on a stream error or sequence gap
    ```

=== "send (fire-and-forget)"

    ```ts
    await mesh.send("audit.logger", { event: "login" });

    // …or with a managed reply callback:
    await mesh.send("billing.charge", { amount: 100 }, {
      onReply: (msg) => ack(msg),
      onError: (err) => warn(err.code, err.message),
    });
    ```

!!! warning "Timeouts are milliseconds"
    Unlike the Python SDK (seconds), the TypeScript client uses milliseconds, the JavaScript norm. Defaults: `call` 30000, `stream` 60000, `send` 60000, `subscribe` none.

`stream` accepts an `AbortSignal` for cancellation:

```ts
const ac = new AbortController();
for await (const chunk of mesh.stream("nlp.summarizer", { url }, { signal: ac.signal })) {
  if (done(chunk)) ac.abort();
}
```

## Publish and subscribe

```ts
// publish to any subject — object → JSON, string → text, Uint8Array → bytes
await mesh.publish("telemetry.uav.42", { x: 10, y: 4 });

// subscribe by agent | channel | subject (exactly one)
for await (const evt of mesh.subscribe({ agent: "weather.station" })) update(evt);
for await (const evt of mesh.subscribe({ channel: "wildfire.fleet" })) update(evt);
```

`subscribe({ agent })` listens on `mesh.agent.<name>.events`; `subscribe({ channel })` listens on `mesh.agent.<channel>.>`.

## Discover agents

Discovery is two-tier: a cheap `catalog()` from a warm, KV-backed cache for selection, then `contract()` for the full schema.

```ts
const agents = await mesh.catalog({ channel: "finance", streaming: true, tags: ["pii"] });
const contract = await mesh.contract("finance.risk.scorer"); // throws NotFound if absent
const fleet = await mesh.discover({ channel: "wildfire.fleet" });
```

The catalog cache is seeded on connect and kept fresh by a KV watch, so `catalog()` is a local, synchronous-feeling read. When the target agent is known, the client runs an ADR-0047 pre-flight check and throws `InvocationMismatch` for a wrong verb (e.g. `call()` on a streaming-only agent).

## Shared-context KV

`mesh.kv` reads and watches the `mesh-context` bucket.

```ts
const state = await mesh.kv.get("wildfire.fire.state");   // throws NotFound if missing
const fleet = await mesh.kv.list("wildfire.fleet.>");     // prefix snapshot

// value watch (decoded strings, on PUT) — mirrors the Python kv.watch:
for await (const value of mesh.kv.watch("wildfire.fire.state")) applyFire(value);

// rich watch (full entries incl. deletes) — for presence/fleet mirrors:
const stop = mesh.kv.watchEntries("wildfire.fleet.>", (e) => {
  if (e.operation === "PUT" && e.value) upsert(e.key, JSON.parse(e.value));
  else remove(e.key);
});
```

Writes use optimistic concurrency: `put`, `create` (put-if-absent, throws `KVKeyExists`), and `update(key, fn)` (CAS with retry). `getModel`/`putModel`/`listModels` accept any structural validator (`{ parse(x): T }`, Zod-compatible) for typed round-trips.

## Errors

All mesh errors derive from `MeshError`. An error reply is reconstructed into the matching subclass; an unknown code falls back to `MeshError` with the code preserved.

```ts
import { MeshError, MeshTimeout, NotFound, InvocationMismatch } from "@openagentmesh/sdk";

try {
  await mesh.call("finance.risk.scorer", { applicant: "A-1023" });
} catch (err) {
  if (err instanceof MeshTimeout) {/* err.subject, err.timeout */}
  else if (err instanceof NotFound) {/* err.agent */}
  else if (err instanceof InvocationMismatch) {/* wrong verb, caught pre-flight */}
  else if (err instanceof MeshError) {/* err.code, err.message, err.details */}
}
```

| Class | Code |
| --- | --- |
| `InvalidInput` | `invalid_input` |
| `HandlerError` | `handler_error` |
| `InvocationMismatch` | `invocation_mismatch` |
| `NotFound` | `not_found` |
| `ConnectionFailed` | `connection_failed` |
| `MeshTimeout` | `timeout` |
| `ChunkSequenceError` | `chunk_sequence_error` |
| `KVKeyExists` | `kv_key_exists` |

!!! note "Unvalidated deserialization"
    Invocation results are returned as plain objects without runtime schema validation; the client is schema-agnostic by design. Validate with `mesh.kv.getModel(key, schema)` or your own validator when you need guarantees.

## Status and scope

This first release is **consume-only**: it invokes and observes agents but does not host them in TypeScript. Agent hosting (handler registration, contract publishing, queue-group serving) is a later addition. See [ADR-0061](https://github.com/openagentmesh/openagentmesh/blob/main/km/adr/0061-typescript-client-sdk.md) for the full design and wire-protocol conformance notes.
