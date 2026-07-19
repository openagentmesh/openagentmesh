import { AbortError, NotFound } from "@openagentmesh/sdk";
import type { AgentContract, CatalogEntry, Json } from "@openagentmesh/sdk";
import type { MeshClient } from "../src/mesh";

/** An async iterable that never yields; ends only when the signal aborts. */
function silent<T>(signal?: AbortSignal): AsyncIterable<T> {
  return {
    [Symbol.asyncIterator]: () => ({
      next: () =>
        new Promise<IteratorResult<T>>((resolve) => {
          signal?.addEventListener("abort", () => resolve({ value: undefined, done: true }), { once: true });
        }),
    }),
  };
}

export const TRANSLATOR: AgentContract = {
  name: "translator",
  description: "Translate text between languages. Uses an LLM under the hood.",
  version: "1.2.0",
  capabilities: { invocable: true, streaming: false },
  skills: [
    {
      id: "translator",
      inputSchema: {
        type: "object",
        properties: { text: { type: "string" }, target_lang: { type: "string" } },
        required: ["text", "target_lang"],
      },
      outputSchema: {
        type: "object",
        properties: { translated: { type: "string" } },
      },
    },
  ],
  subject: "mesh.agent.translator",
  tags: ["nlp", "demo"],
  invocable: true,
  streaming: false,
  inputSchema: {
    type: "object",
    properties: { text: { type: "string" }, target_lang: { type: "string" } },
    required: ["text", "target_lang"],
  },
  outputSchema: {
    type: "object",
    properties: { translated: { type: "string" } },
  },
  registeredAt: "2026-07-19T08:00:00Z",
};

export const TICKER: AgentContract = {
  name: "ticker",
  description: "Stream market ticks for a symbol.",
  version: "0.3.1",
  capabilities: { invocable: true, streaming: true },
  skills: [{ id: "ticker" }],
  subject: "mesh.agent.ticker",
  tags: ["finance"],
  invocable: true,
  streaming: true,
  chunkSchema: { type: "object", properties: { price: { type: "number" } } },
};

/** Trigger shape (ADR-0031): invocable, no input schema — a bare "run it" agent. */
export const REINDEXER: AgentContract = {
  name: "reindexer",
  description: "Rebuild the search index from scratch.",
  version: "2.0.0",
  capabilities: { invocable: true, streaming: false },
  skills: [{ id: "reindexer" }],
  subject: "mesh.agent.reindexer",
  tags: [],
  invocable: true,
  streaming: false,
  outputSchema: { type: "object", properties: { indexed: { type: "number" } } },
};

/** Source-only shape (ADR-0031): publishes events, cannot be invoked at all. */
export const AUDIT_LOG: AgentContract = {
  name: "audit-log",
  description: "Publishes an audit event for every mesh invocation.",
  version: "1.0.0",
  capabilities: { invocable: false, streaming: false },
  skills: [{ id: "audit-log" }],
  subject: "mesh.agent.audit-log",
  tags: ["ops"],
  invocable: false,
  streaming: false,
};

function toCatalogEntry(c: AgentContract): CatalogEntry {
  return {
    name: c.name,
    description: c.description,
    version: c.version,
    tags: c.tags,
    invocable: c.invocable,
    streaming: c.streaming,
  };
}

/** In-memory MeshClient backed by a fixed contract list; invocation stubs via `overrides`. */
export function fakeMesh(
  contracts: AgentContract[] = [TRANSLATOR, TICKER],
  overrides: Partial<MeshClient> = {},
): MeshClient {
  return {
    catalog: async () => contracts.map(toCatalogEntry),
    contract: async (name: string) => {
      const found = contracts.find((c) => c.name === name);
      if (!found) throw new NotFound(`Agent '${name}' not found`, { agent: name });
      return found;
    },
    call: async (name: string) => {
      throw new Error(`fakeMesh.call('${name}') not stubbed — pass overrides.call`);
    },
    stream: (name: string) => {
      throw new Error(`fakeMesh.stream('${name}') not stubbed — pass overrides.stream`);
    },
    close: async () => {},
    tap: (_subject, opts) => silent(opts?.signal),
    instancesWatch: (opts) => silent(opts?.signal),
    ...overrides,
  };
}

/**
 * Externally-driven chunk source for stream tests: `push` chunks one at a
 * time, `end`/`fail` to terminate. `iterate(signal)` mirrors the SDK stream's
 * abort semantics (pending next() rejects with AbortError on abort).
 */
export function pushableQueue<T = Json>() {
  const buffered: T[] = [];
  let ended = false;
  let failure: unknown;
  let pending: { resolve: (r: IteratorResult<T, undefined>) => void; reject: (e: unknown) => void } | null = null;

  return {
    push(chunk: T) {
      if (pending) {
        pending.resolve({ value: chunk, done: false });
        pending = null;
      } else buffered.push(chunk);
    },
    end() {
      ended = true;
      if (pending) {
        pending.resolve({ value: undefined, done: true });
        pending = null;
      }
    },
    fail(err: unknown) {
      failure = err;
      if (pending) {
        pending.reject(err);
        pending = null;
      }
    },
    iterate(signal?: AbortSignal): AsyncIterable<T> {
      const next = (): Promise<IteratorResult<T, undefined>> => {
        if (buffered.length > 0) return Promise.resolve({ value: buffered.shift() as T, done: false });
        if (failure !== undefined) return Promise.reject(failure);
        if (ended) return Promise.resolve({ value: undefined, done: true });
        if (signal?.aborted) return Promise.reject(new AbortError());
        return new Promise((resolve, reject) => {
          pending = { resolve, reject };
          signal?.addEventListener(
            "abort",
            () => {
              if (pending?.reject === reject) {
                pending = null;
                reject(new AbortError());
              }
            },
            { once: true },
          );
        });
      };
      return { [Symbol.asyncIterator]: () => ({ next }) };
    },
  };
}
