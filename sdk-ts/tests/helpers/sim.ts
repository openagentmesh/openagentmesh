// Wire-level agent simulator: emulates the Python agent side over real NATS so
// the TypeScript client can be tested end-to-end against the actual protocol.
import { Kvm } from "@nats-io/kv";
import { headers, type Msg, type NatsConnection, type Subscription } from "@nats-io/nats-core";
import { connect } from "@nats-io/transport-node";

const ENC = new TextEncoder();
const DEC = new TextDecoder();
const enc = (v: unknown) => ENC.encode(JSON.stringify(v));
const dec = (d: Uint8Array) => (d.length ? JSON.parse(DEC.decode(d)) : {});
/** Decode best-effort: JSON when possible, else the raw bytes (for text/binary payloads). */
const tryDec = (d: Uint8Array): unknown => {
  if (!d.length) return {};
  try {
    return JSON.parse(DEC.decode(d));
  } catch {
    return d;
  }
};

export function rawConnect(url: string): Promise<NatsConnection> {
  return connect({ servers: url });
}

const agentSubject = (name: string) => `mesh.agent.${name}`;
const eventSubject = (name: string) => `mesh.agent.${name}.events`;
const streamSubject = (reqId: string) => `mesh.stream.${reqId}`;

function reqId(m: Msg): string {
  return m.headers?.get("X-Mesh-Request-Id") ?? "";
}
function isStreamRequest(m: Msg): boolean {
  return m.headers?.get("X-Mesh-Stream") === "true";
}

export interface ErrorResult {
  __error: { code: string; message: string; agent?: string; request_id?: string; details?: Record<string, unknown> };
}
export function errorResult(code: string, message: string, details?: Record<string, unknown>): ErrorResult {
  return { __error: { code, message, ...(details ? { details } : {}) } };
}

/** Tracks subscriptions created by sim helpers so a suite can tear them down. */
export class Sim {
  readonly subs: Subscription[] = [];
  constructor(readonly nc: NatsConnection) {}

  /** Respond to call()/send() with the handler's return value (or an ErrorResult). */
  responder(name: string, handler: (payload: any, m: Msg) => unknown): this {
    const sub = this.nc.subscribe(agentSubject(name), { queue: `q.${name}` });
    this.subs.push(sub);
    void (async () => {
      for await (const m of sub) {
        if (isStreamRequest(m)) continue;
        const out = handler(dec(m.data), m);
        const h = headers();
        h.set("X-Mesh-Request-Id", reqId(m));
        if (out && typeof out === "object" && "__error" in (out as object)) {
          const e = (out as ErrorResult).__error;
          h.set("X-Mesh-Status", "error");
          if (m.reply) m.respond(enc({ ...e, agent: e.agent ?? name, request_id: e.request_id ?? reqId(m) }), { headers: h });
        } else {
          h.set("X-Mesh-Status", "ok");
          h.set("X-Mesh-Source", name);
          if (m.reply) m.respond(enc(out ?? {}), { headers: h });
        }
      }
    })();
    return this;
  }

  /** Stream chunks back on mesh.stream.{reqId} when the agent is invoked with X-Mesh-Stream: true. */
  streamer(name: string, chunksFor: (payload: any) => unknown[]): this {
    const sub = this.nc.subscribe(agentSubject(name), { queue: `q.${name}` });
    this.subs.push(sub);
    void (async () => {
      for await (const m of sub) {
        if (!isStreamRequest(m)) continue;
        const id = reqId(m);
        const chunks = chunksFor(dec(m.data));
        chunks.forEach((c, i) => {
          const h = headers();
          h.set("X-Mesh-Request-Id", id);
          h.set("X-Mesh-Stream-Seq", String(i));
          h.set("X-Mesh-Stream-End", "false");
          this.nc.publish(streamSubject(id), enc(c), { headers: h });
        });
        const ht = headers();
        ht.set("X-Mesh-Request-Id", id);
        ht.set("X-Mesh-Stream-Seq", String(chunks.length));
        ht.set("X-Mesh-Stream-End", "true");
        this.nc.publish(streamSubject(id), new Uint8Array(0), { headers: ht });
        await this.nc.flush();
      }
    })();
    return this;
  }

  /** Emit an error mid-stream after `okChunks` good chunks. */
  streamerError(name: string, okChunks: unknown[], err: ErrorResult["__error"]): this {
    const sub = this.nc.subscribe(agentSubject(name), { queue: `q.${name}` });
    this.subs.push(sub);
    void (async () => {
      for await (const m of sub) {
        if (!isStreamRequest(m)) continue;
        const id = reqId(m);
        okChunks.forEach((c, i) => {
          const h = headers();
          h.set("X-Mesh-Request-Id", id);
          h.set("X-Mesh-Stream-Seq", String(i));
          h.set("X-Mesh-Stream-End", "false");
          this.nc.publish(streamSubject(id), enc(c), { headers: h });
        });
        const he = headers();
        he.set("X-Mesh-Request-Id", id);
        he.set("X-Mesh-Status", "error");
        he.set("X-Mesh-Stream-End", "true");
        this.nc.publish(streamSubject(id), enc({ ...err, agent: name }), { headers: he });
        await this.nc.flush();
      }
    })();
    return this;
  }

  /** Capture the next message published to an agent's invocation subject (for fire-and-forget asserts). */
  capture(name: string, onMsg: (payload: any, m: Msg) => void): this {
    const sub = this.nc.subscribe(agentSubject(name), { queue: `q.${name}` });
    this.subs.push(sub);
    void (async () => {
      for await (const m of sub) onMsg(tryDec(m.data), m);
    })();
    return this;
  }

  /** Capture messages on an arbitrary subject (for publish() asserts). */
  captureSubject(subject: string, onMsg: (payload: any, m: Msg) => void): this {
    const sub = this.nc.subscribe(subject);
    this.subs.push(sub);
    void (async () => {
      for await (const m of sub) onMsg(tryDec(m.data), m);
    })();
    return this;
  }

  /** Flush the underlying connection so a freshly-created subscription's interest reaches the server. */
  async ready(): Promise<void> {
    await this.nc.flush();
  }

  /** Stream chunks but with a gap in the sequence numbers to force a ChunkSequenceError. */
  streamerBadSeq(name: string, chunks: unknown[]): this {
    const sub = this.nc.subscribe(agentSubject(name), { queue: `q.${name}` });
    this.subs.push(sub);
    void (async () => {
      for await (const m of sub) {
        if (!isStreamRequest(m)) continue;
        const id = reqId(m);
        chunks.forEach((c, i) => {
          const seq = i === 0 ? 0 : i + 1; // 0, 2, 3, ... → gap after the first chunk
          const h = headers();
          h.set("X-Mesh-Request-Id", id);
          h.set("X-Mesh-Stream-Seq", String(seq));
          h.set("X-Mesh-Stream-End", "false");
          this.nc.publish(streamSubject(id), enc(c), { headers: h });
        });
        await this.nc.flush();
      }
    })();
    return this;
  }

  /** Publish an event to an agent's `.events` subject (optionally framed as a stream). */
  async emitEvent(name: string, payload: unknown, opts: { seq?: number; end?: boolean } = {}): Promise<void> {
    const h = headers();
    if (opts.seq !== undefined) h.set("X-Mesh-Stream-Seq", String(opts.seq));
    if (opts.end) h.set("X-Mesh-Stream-End", "true");
    this.nc.publish(eventSubject(name), enc(payload), { headers: h });
    await this.nc.flush();
  }

  /** Publish a raw payload to an arbitrary subject (for subscribe-by-subject tests). */
  async emitSubject(subject: string, payload: unknown, opts: { end?: boolean } = {}): Promise<void> {
    const h = headers();
    if (opts.end) h.set("X-Mesh-Stream-End", "true");
    this.nc.publish(subject, enc(payload), { headers: h });
    await this.nc.flush();
  }

  async drain(): Promise<void> {
    for (const s of this.subs) s.unsubscribe();
  }
}

// ── KV seeding ────────────────────────────────────────────────────────────────

export async function ensureBuckets(nc: NatsConnection): Promise<void> {
  const kvm = new Kvm(nc);
  await kvm.create("mesh-catalog", { history: 5 });
  await kvm.create("mesh-registry", { history: 5 });
  await kvm.create("mesh-context", { history: 10 });
}

export async function seedCatalog(nc: NatsConnection, entries: Array<Record<string, unknown>>): Promise<void> {
  const kvm = new Kvm(nc);
  const kv = await kvm.open("mesh-catalog");
  await kv.put("catalog", enc(entries));
}

export async function seedContract(nc: NatsConnection, name: string, contract: Record<string, unknown>): Promise<void> {
  const kvm = new Kvm(nc);
  const kv = await kvm.open("mesh-registry");
  await kv.put(name, enc(contract));
}

export async function putContext(nc: NatsConnection, key: string, value: unknown): Promise<number> {
  const kvm = new Kvm(nc);
  const kv = await kvm.open("mesh-context");
  return kv.put(key, typeof value === "string" ? ENC.encode(value) : enc(value));
}
