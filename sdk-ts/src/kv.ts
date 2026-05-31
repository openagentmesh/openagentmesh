import type { KV } from "@nats-io/kv";
import { encodeJSON, encodeText } from "./codec.js";
import { KVKeyExists, NotFound } from "./errors.js";
import type { KvSnapshotEntry, KvWatchEntry, Validator } from "./types.js";

export const CONTEXT_BUCKET = "mesh-context";

function toBytes(value: unknown): Uint8Array {
  if (value instanceof Uint8Array) return value;
  if (typeof value === "string") return encodeText(value);
  return encodeJSON(value);
}

function isWrongLastSequence(err: unknown): boolean {
  const e = err as { code?: number | string; api_error?: { err_code?: number }; message?: string };
  if (e?.api_error?.err_code === 10071) return true;
  if (e?.code === 10071) return true;
  return /wrong last sequence|already exists/i.test(e?.message ?? "");
}

function normOp(op: "PUT" | "DEL" | "PURGE"): "PUT" | "DELETE" {
  return op === "PUT" ? "PUT" : "DELETE";
}

/**
 * Shared-context KV store over the `mesh-context` bucket. Consume-focused
 * (get/list/watch) with optimistic-concurrency writes (put/create/update).
 */
export class KVStore {
  constructor(private readonly kv: KV) {}

  /** Decoded string value. Throws `NotFound` if the key is missing/deleted. */
  async get(key: string): Promise<string> {
    const e = await this.kv.get(key);
    if (!e || e.operation !== "PUT" || e.value.length === 0) {
      throw new NotFound(`KV key '${key}' not found`, { details: { key } });
    }
    return e.string();
  }

  async getModel<T>(key: string, validator: Validator<T>): Promise<T> {
    return validator.parse(JSON.parse(await this.get(key)));
  }

  /** One-shot snapshot of all PUT entries under a key/wildcard prefix. */
  async list(prefix: string): Promise<KvSnapshotEntry[]> {
    const keysIter = await this.kv.keys(prefix);
    const keys: string[] = [];
    for await (const k of keysIter) keys.push(k);

    const out: KvSnapshotEntry[] = [];
    for (const k of keys) {
      const e = await this.kv.get(k);
      if (e && e.operation === "PUT" && e.value.length > 0) {
        out.push({ key: e.key, value: e.string(), revision: e.revision, operation: "PUT" });
      }
    }
    return out;
  }

  async listModels<T>(prefix: string, validator: Validator<T>): Promise<Array<{ key: string; value: T; revision: number }>> {
    const rows = await this.list(prefix);
    return rows.map((r) => ({ key: r.key, value: validator.parse(JSON.parse(r.value)), revision: r.revision }));
  }

  /** Async iterator of decoded string values on each PUT (mirrors Python kv.watch). */
  async *watch(key: string): AsyncIterable<string> {
    const iter = await this.kv.watch({ key, ignoreDeletes: true });
    for await (const e of iter) {
      if (e.operation === "PUT" && e.value.length > 0) yield e.string();
    }
  }

  /** Rich watch over a key/prefix yielding full entries (incl. deletes). Returns a stop fn. */
  watchEntries(prefix: string, cb: (e: KvWatchEntry) => void): () => void {
    let stopped = false;
    let stopIter: (() => void) | undefined;
    void (async () => {
      const iter = await this.kv.watch({ key: prefix });
      stopIter = () => iter.stop();
      for await (const e of iter) {
        if (stopped) break;
        const operation = normOp(e.operation);
        cb({
          key: e.key,
          value: operation === "PUT" ? e.string() : null,
          revision: e.revision,
          operation,
        });
      }
    })();
    return () => {
      stopped = true;
      stopIter?.();
    };
  }

  /** Store a value (object → JSON, string → text, bytes → as-is). Returns the new revision. */
  async put(key: string, value: unknown): Promise<number> {
    return this.kv.put(key, toBytes(value));
  }

  async putModel(key: string, value: unknown): Promise<number> {
    return this.kv.put(key, encodeJSON(value));
  }

  /** Put-if-absent. Throws `KVKeyExists` if the key already exists. */
  async create(key: string, value: unknown): Promise<number> {
    try {
      return await this.kv.create(key, toBytes(value));
    } catch (err) {
      if (isWrongLastSequence(err)) {
        throw new KVKeyExists(`KV key '${key}' already exists`, { key });
      }
      throw err;
    }
  }

  async delete(key: string): Promise<void> {
    await this.kv.delete(key);
  }

  /** CAS-retry update: read, apply `fn`, compare-and-set, retry on conflict. */
  async update(
    key: string,
    fn: (current: string) => string | Promise<string>,
    opts: { maxRetries?: number } = {},
  ): Promise<void> {
    const maxRetries = opts.maxRetries ?? 10;
    for (let i = 0; i < maxRetries; i++) {
      const e = await this.kv.get(key);
      const current = e && e.operation === "PUT" ? e.string() : "";
      const revision = e ? e.revision : 0;
      const next = await fn(current);
      try {
        await this.kv.put(key, toBytes(next), { previousSeq: revision });
        return;
      } catch (err) {
        if (isWrongLastSequence(err)) continue;
        throw err;
      }
    }
    throw new Error(`kv.update exhausted ${maxRetries} retries for key '${key}'`);
  }
}
