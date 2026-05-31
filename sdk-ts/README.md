# @openagentmesh/sdk

TypeScript client SDK for [OpenAgentMesh](https://github.com/) — the fabric for multi-agent systems, with the simplicity of a REST endpoint.

Isomorphic (browser + Node). **Consume-only**: it invokes and observes agents on a mesh; it does not host them. Speaks the exact OAM wire protocol over the [`@nats-io`](https://github.com/nats-io/nats.js) v3 client — WebSocket in the browser, TCP in Node.

## Install

```sh
pnpm add @openagentmesh/sdk @nats-io/nats-core @nats-io/jetstream @nats-io/kv
# Node (TCP) also needs the node transport:
pnpm add @nats-io/transport-node
```

## Quickstart

```ts
import { AgentMesh } from "@openagentmesh/sdk";

// Browser: ws:// picks the WebSocket transport. Node: nats:// picks TCP.
const mesh = await AgentMesh.connect({ servers: "nats://127.0.0.1:4222" });

// request/reply
const score = await mesh.call("finance.risk.scorer", { applicant: "A-1023" });

// streaming
for await (const chunk of mesh.stream("nlp.summarizer", { url })) render(chunk);

// fire-and-forget, or a managed reply callback
await mesh.send("audit.logger", { event: "login" });
await mesh.send("billing.charge", { amount: 100 }, { onReply: ack, onError: warn });

// publish to an arbitrary subject (object → JSON, string → text, Uint8Array → bytes)
await mesh.publish("telemetry.uav.42", { x: 10, y: 4 });

// subscribe to events by agent | channel | subject (exactly one)
for await (const evt of mesh.subscribe({ channel: "wildfire.fleet" })) update(evt);

// discovery: cheap catalog → full contract
const agents = await mesh.catalog({ channel: "finance", streaming: true });
const contract = await mesh.contract("finance.risk.scorer");

// shared-context KV (mesh-context bucket)
const state = await mesh.kv.get("wildfire.fire.state");
for await (const v of mesh.kv.watch("wildfire.fire.state")) applyFire(v);

await mesh.close();
```

In the browser, pass `{ configUrl: "/config.json" }` to bootstrap the WebSocket URL from a `{ nats_ws_url }` document instead of hard-coding `servers`.

## API

| Method | Purpose |
| --- | --- |
| `AgentMesh.connect(opts)` | Open a connection. `opts.servers` (string \| string[]) or `opts.configUrl`. |
| `mesh.instanceId` | Stable per-process id, stamped as `X-Mesh-Instance-Id` on every outbound message. |
| `mesh.call(name, payload?, { timeout? })` | Request/reply. Returns the reply object; throws a typed error on an error reply. |
| `mesh.stream(name, payload?, { timeout?, signal? })` | Async iterable of chunks; validates sequence, throws on stream error. |
| `mesh.send(name, payload?, { onReply?, onError?, replyTo?, timeout? })` | Fire-and-forget or managed reply. |
| `mesh.publish(subject, payload, { headers? })` | Publish to an arbitrary subject (no wildcards). |
| `mesh.subscribe({ agent? \| channel? \| subject?, timeout?, signal? })` | Async iterable of events. |
| `mesh.catalog({ channel?, tags?, streaming?, invocable? })` | Lightweight discovery from the warm cache. |
| `mesh.contract(name)` | Full `AgentContract` (throws `NotFound`). |
| `mesh.discover({ channel? })` | Contracts for matching agents. |
| `mesh.kv` | Shared-context `KVStore`: `get`, `list`, `watch`, `watchEntries`, `put`, `create`, `update`, `delete`, plus `getModel`/`putModel`/`listModels`. |
| `mesh.close()` | Drain subscriptions and close. |

**Timeouts are milliseconds** (idiomatic JS): defaults `call` 30000, `stream` 60000, `send` 60000, `subscribe` none.

### Errors

`MeshError` (base) and subclasses `InvalidInput`, `HandlerError`, `InvocationMismatch`, `NotFound`, `ConnectionFailed`, `MeshTimeout`, `ChunkSequenceError`, `KVKeyExists`. An error reply (`X-Mesh-Status: error`) is reconstructed into the matching class; an unknown code falls back to `MeshError` with the code preserved.

```ts
import { MeshTimeout, NotFound, InvocationMismatch, MeshError } from "@openagentmesh/sdk";
try {
  await mesh.call("finance.risk.scorer", { applicant: "A-1023" });
} catch (err) {
  if (err instanceof MeshTimeout) {/* err.subject, err.timeout */}
  else if (err instanceof NotFound) {/* err.agent */}
  else if (err instanceof MeshError) {/* err.code, err.message, err.details */}
}
```

## Development

```sh
pnpm install
pnpm test        # Vitest against a real nats-server (~/.agentmesh/bin/nats-server)
pnpm build       # tsc → dist/
pnpm typecheck
```

Tests spawn a JetStream-enabled `nats-server` per file and pair the client with a wire-level agent simulator, so they exercise the real protocol over real NATS.

See [ADR-0061](../km/adr/0061-typescript-client-sdk.md) for design rationale and the wire-protocol conformance notes.
