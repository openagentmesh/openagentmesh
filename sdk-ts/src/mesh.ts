import { Kvm } from "@nats-io/kv";
import type { Msg, NatsConnection, Subscription } from "@nats-io/nats-core";
import { decodeJSON, encodeJSON, encodeText } from "./codec.js";
import { openConnection } from "./connection.js";
import {
  CATALOG_BUCKET,
  Discovery,
  REGISTRY_BUCKET,
} from "./discovery.js";
import {
  ChunkSequenceError,
  type ErrorEnvelope,
  fromEnvelope,
  InvalidInput,
  InvocationMismatch,
  MeshError,
  MeshTimeout,
  NotFound,
} from "./errors.js";
import { buildHeaders, H, readHeader, STATUS_ERROR } from "./headers.js";
import { CONTEXT_BUCKET, KVStore } from "./kv.js";
import {
  channelSubject,
  computeEventSubject,
  computeSubject,
  isValidSubject,
  newRequestId,
  resultsSubject,
  streamSubject,
} from "./subjects.js";
import type {
  AgentContract,
  CallOptions,
  CatalogEntry,
  CatalogFilter,
  ConnectOptions,
  Json,
  PublishOptions,
  SendOptions,
  StreamOptions,
  SubscribeOptions,
} from "./types.js";
import { isNoRespondersError, isTimeoutError, withAbort, withDeadline } from "./util.js";

type Verb = "call" | "stream" | "send" | "subscribe";

/** Best-effort ADR-0047 capability check from catalog flags. */
function capabilityError(verb: Verb, e: CatalogEntry): string | undefined {
  switch (verb) {
    case "call":
      if (!e.invocable) return "is not invocable and cannot be called";
      if (e.streaming) return "is streaming-only. Use stream() instead";
      return undefined;
    case "stream":
      if (!e.streaming) return "does not support streaming. Use call() instead";
      return undefined;
    case "send":
      if (!e.invocable) return "is not invocable and cannot be sent to";
      return undefined;
    case "subscribe":
      if (e.invocable && e.streaming) return "streams responses to requests. Use stream() instead";
      return undefined;
  }
}

export class AgentMesh {
  readonly instanceId: string = newRequestId();
  private discovery?: Discovery;
  private _kv?: KVStore;

  private constructor(private readonly nc: NatsConnection) {}

  static async connect(opts: ConnectOptions): Promise<AgentMesh> {
    const nc = await openConnection(opts);
    const mesh = new AgentMesh(nc);
    await mesh.initStores(opts.watchCatalog !== false);
    return mesh;
  }

  /** Underlying NATS connection (escape hatch). */
  get connection(): NatsConnection {
    return this.nc;
  }

  get kv(): KVStore {
    if (!this._kv) {
      throw new MeshError("KV unavailable: 'mesh-context' bucket not found", { code: "connection_failed" });
    }
    return this._kv;
  }

  private async initStores(watch: boolean): Promise<void> {
    const kvm = new Kvm(this.nc);
    try {
      const catalogKv = await kvm.open(CATALOG_BUCKET);
      const registryKv = await kvm.open(REGISTRY_BUCKET);
      this.discovery = new Discovery(catalogKv, registryKv);
      await this.discovery.seed();
      if (watch) this.discovery.startWatch();
    } catch {
      /* discovery buckets absent — catalog() yields [], contract() throws NotFound */
    }
    try {
      const ctxKv = await kvm.open(CONTEXT_BUCKET);
      this._kv = new KVStore(ctxKv);
    } catch {
      /* mesh-context bucket absent — `mesh.kv` throws on use */
    }
  }

  private preflight(name: string, verb: Verb): void {
    const entry = this.discovery?.cachedEntry(name);
    if (!entry) return; // unknown locally → let the request go out
    const why = capabilityError(verb, entry);
    if (why) throw new InvocationMismatch(`Agent '${name}' ${why}`, { agent: name });
  }

  private readReply(reply: Msg): Json {
    if (readHeader(reply.headers, H.status) === STATUS_ERROR) {
      throw fromEnvelope(decodeJSON<ErrorEnvelope>(reply.data));
    }
    return decodeJSON(reply.data);
  }

  // ── call ────────────────────────────────────────────────────────────────
  async call(name: string, payload?: unknown, opts: CallOptions = {}): Promise<Json> {
    const timeout = opts.timeout ?? 30_000;
    this.preflight(name, "call");
    const requestId = newRequestId();
    const subject = computeSubject(name);
    const headers = buildHeaders({ [H.requestId]: requestId }, this.instanceId);
    try {
      const reply = await this.nc.request(subject, encodeJSON(payload), { timeout, headers });
      return this.readReply(reply);
    } catch (err) {
      if (err instanceof MeshError) throw err;
      if (isNoRespondersError(err)) {
        throw new NotFound(`No agent serving '${name}'`, { agent: name, requestId });
      }
      if (isTimeoutError(err)) {
        throw new MeshTimeout(`call to '${name}' timed out after ${timeout}ms`, {
          subject,
          timeout,
          agent: name,
          requestId,
        });
      }
      throw err;
    }
  }

  // ── stream ──────────────────────────────────────────────────────────────
  async *stream(name: string, payload?: unknown, opts: StreamOptions = {}): AsyncIterable<Json> {
    const timeout = opts.timeout ?? 60_000;
    this.preflight(name, "stream");
    const requestId = newRequestId();
    const subj = streamSubject(requestId);
    const sub = this.nc.subscribe(subj); // subscribe BEFORE publishing the request
    try {
      const headers = buildHeaders({ [H.requestId]: requestId, [H.stream]: "true" }, this.instanceId);
      this.nc.publish(computeSubject(name), encodeJSON(payload), { headers });

      const it = sub[Symbol.asyncIterator]();
      let expected = 0;
      const deadline = Date.now() + timeout;
      while (true) {
        const remaining = deadline - Date.now();
        if (remaining <= 0) {
          throw new MeshTimeout(`stream from '${name}' timed out after ${timeout}ms`, { subject: subj, timeout, agent: name });
        }
        const res = await withDeadline(
          it.next(),
          remaining,
          () => new MeshTimeout(`stream from '${name}' timed out after ${timeout}ms`, { subject: subj, timeout, agent: name }),
          opts.signal,
        );
        if (res.done) break;
        const m = res.value;
        // Error chunks are exempt from sequence validation (they carry
        // X-Mesh-Status:error + X-Mesh-Stream-End:true and terminate the stream),
        // matching the Python SDK which omits X-Mesh-Stream-Seq on error chunks.
        if (readHeader(m.headers, H.status) === STATUS_ERROR) {
          throw fromEnvelope(decodeJSON<ErrorEnvelope>(m.data));
        }
        if (readHeader(m.headers, H.streamEnd) === "true") break;
        const seqStr = readHeader(m.headers, H.streamSeq);
        const seq = seqStr === undefined ? expected : Number.parseInt(seqStr, 10);
        if (seq !== expected) {
          throw new ChunkSequenceError(`out-of-order chunk from '${name}'`, { agent: name, expectedSeq: expected, gotSeq: seq });
        }
        expected += 1;
        yield decodeJSON(m.data);
      }
    } finally {
      sub.unsubscribe();
    }
  }

  // ── send ────────────────────────────────────────────────────────────────
  async send(name: string, payload?: unknown, opts: SendOptions = {}): Promise<void> {
    const timeout = opts.timeout ?? 60_000;
    this.preflight(name, "send");
    if (opts.onReply && opts.replyTo) {
      throw new InvalidInput("send(): `onReply` and `replyTo` are mutually exclusive");
    }
    const requestId = newRequestId();
    const subject = computeSubject(name);
    const data = encodeJSON(payload);

    if (opts.onReply) {
      const replySubj = resultsSubject(requestId);
      const sub = this.nc.subscribe(replySubj);
      void this.drainReplies(sub, opts, timeout).catch(() => {
        /* drain is fire-and-forget; failures are surfaced via onError */
      });
      const headers = buildHeaders({ [H.requestId]: requestId }, this.instanceId);
      this.nc.publish(subject, data, { headers, reply: replySubj });
      return;
    }
    if (opts.replyTo) {
      const headers = buildHeaders({ [H.requestId]: requestId, [H.replyTo]: opts.replyTo }, this.instanceId);
      this.nc.publish(subject, data, { headers, reply: opts.replyTo });
      return;
    }
    const headers = buildHeaders({ [H.requestId]: requestId }, this.instanceId);
    this.nc.publish(subject, data, { headers });
  }

  private async drainReplies(sub: Subscription, opts: SendOptions, timeout: number): Promise<void> {
    // Consumer callbacks run inside this background task; isolate their throws
    // so a buggy onReply/onError cannot become an unhandled rejection.
    const safeReply = (msg: Json): void => {
      try {
        opts.onReply?.(msg);
      } catch {
        /* swallow consumer callback error */
      }
    };
    const safeError = (err: MeshError): void => {
      try {
        opts.onError?.(err);
      } catch {
        /* swallow consumer callback error */
      }
    };
    try {
      const it = sub[Symbol.asyncIterator]();
      const deadline = Date.now() + timeout;
      while (true) {
        const remaining = deadline - Date.now();
        if (remaining <= 0) {
          safeError(new MeshTimeout(`send reply timed out after ${timeout}ms`, { timeout }));
          break;
        }
        let res: IteratorResult<Msg>;
        try {
          res = await withDeadline(it.next(), remaining, () => new MeshTimeout(`send reply timed out after ${timeout}ms`, { timeout }));
        } catch (err) {
          safeError(err instanceof MeshError ? err : new MeshError(String(err)));
          break;
        }
        if (res.done) break;
        const m = res.value;
        if (readHeader(m.headers, H.status) === STATUS_ERROR) {
          safeError(fromEnvelope(decodeJSON<ErrorEnvelope>(m.data)));
          break;
        }
        safeReply(decodeJSON(m.data));
        const hasSeq = readHeader(m.headers, H.streamSeq) !== undefined;
        const ended = readHeader(m.headers, H.streamEnd) === "true";
        if (!hasSeq || ended) break;
      }
    } finally {
      sub.unsubscribe();
    }
  }

  // ── publish ───────────────────────────────────────────────────────────────
  async publish(subject: string, payload: unknown, opts: PublishOptions = {}): Promise<void> {
    if (!isValidSubject(subject)) {
      throw new InvalidInput(`invalid publish subject '${subject}' (wildcards are not allowed)`);
    }
    let data: Uint8Array;
    let contentType: string;
    if (payload instanceof Uint8Array) {
      data = payload;
      contentType = "application/octet-stream";
    } else if (typeof payload === "string") {
      data = encodeText(payload);
      contentType = "text/plain";
    } else {
      data = encodeJSON(payload);
      contentType = "application/json";
    }
    const headers = buildHeaders(
      { [H.requestId]: newRequestId(), [H.contentType]: contentType },
      this.instanceId,
      opts.headers,
    );
    this.nc.publish(subject, data, { headers });
  }

  // ── subscribe ─────────────────────────────────────────────────────────────
  async *subscribe(opts: SubscribeOptions): AsyncIterable<Json> {
    const subject = this.resolveSubscribeSubject(opts);
    if (opts.agent) this.preflight(opts.agent, "subscribe");
    const sub = this.nc.subscribe(subject);
    try {
      const it = sub[Symbol.asyncIterator]();
      while (true) {
        const res =
          opts.timeout !== undefined
            ? await withDeadline(
                it.next(),
                opts.timeout,
                () => new MeshTimeout(`subscribe to '${subject}' timed out after ${opts.timeout}ms`, { subject, timeout: opts.timeout }),
                opts.signal,
              )
            : await withAbort(it.next(), opts.signal);
        if (res.done) break;
        const m = res.value;
        if (readHeader(m.headers, H.status) === STATUS_ERROR) {
          throw fromEnvelope(decodeJSON<ErrorEnvelope>(m.data));
        }
        yield decodeJSON(m.data);
        if (readHeader(m.headers, H.streamEnd) === "true") break;
      }
    } finally {
      sub.unsubscribe();
    }
  }

  private resolveSubscribeSubject(opts: SubscribeOptions): string {
    if (opts.subject && opts.agent) {
      throw new InvalidInput("subscribe(): `agent` and `subject` are mutually exclusive");
    }
    if (opts.subject) return opts.subject;
    if (opts.agent) return computeEventSubject(opts.agent);
    if (opts.channel) return channelSubject(opts.channel);
    throw new InvalidInput("subscribe(): one of `agent`, `channel`, or `subject` is required");
  }

  // ── discovery ──────────────────────────────────────────────────────────────
  async catalog(filter: CatalogFilter = {}): Promise<CatalogEntry[]> {
    return this.discovery ? this.discovery.catalog(filter) : [];
  }

  async contract(name: string): Promise<AgentContract> {
    if (!this.discovery) throw new NotFound(`Agent '${name}' not found`, { agent: name });
    return this.discovery.contract(name);
  }

  async discover(opts: { channel?: string } = {}): Promise<AgentContract[]> {
    return this.discovery ? this.discovery.discover(opts.channel) : [];
  }

  // ── lifecycle ──────────────────────────────────────────────────────────────
  async close(): Promise<void> {
    this.discovery?.stop();
    await this.nc.drain();
  }
}
