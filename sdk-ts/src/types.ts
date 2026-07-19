// Public data shapes for the OAM TypeScript client.
import type { MeshError } from "./errors.js";

export type Json = Record<string, unknown>;

/** Lightweight discovery entry (tier 1). Mirrors `CatalogEntry` JSON. */
export interface CatalogEntry {
  name: string;
  description: string;
  version: string;
  tags: string[];
  invocable: boolean;
  streaming: boolean;
}

/** Full agent contract (tier 2). A2A-compatible with OAM fields. */
export interface AgentContract {
  name: string;
  description: string;
  version: string;
  capabilities: Record<string, unknown>;
  skills: Array<Record<string, unknown>>;
  subject: string;
  tags: string[];
  invocable: boolean;
  streaming: boolean;
  /** Sourced from skills[0].inputSchema (improves on the Python gap). */
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  /** x-agentmesh.chunk_schema (streaming agents only). */
  chunkSchema?: Record<string, unknown>;
  /** x-agentmesh.registered_at (ISO-8601). */
  registeredAt?: string;
}

/** Snapshot entry from `kv.list()`. Operation normalized to PUT/DELETE. */
export interface KvSnapshotEntry {
  key: string;
  value: string;
  revision: number;
  operation: "PUT" | "DELETE";
}

/** Live entry from `kv.watchEntries()`. `value` is null on a delete. */
export interface KvWatchEntry {
  key: string;
  value: string | null;
  revision: number;
  operation: "PUT" | "DELETE";
}

export interface ConnectOptions {
  /** Server URL(s). `ws://`/`wss://` → WebSocket transport; `nats://`/`tls://` → Node TCP. */
  servers?: string | string[];
  /** Browser convenience: fetch this URL for `{ nats_ws_url }` and connect to it. */
  configUrl?: string;
  /** Optional client label. */
  name?: string;
  /** Eagerly seed + watch the catalog cache on connect (default true). */
  watchCatalog?: boolean;
}

export interface CallOptions {
  timeout?: number;
}

export interface StreamOptions {
  timeout?: number;
  signal?: AbortSignal;
}

export interface SendOptions {
  onReply?: (msg: Json) => void;
  onError?: (err: MeshError) => void;
  replyTo?: string;
  timeout?: number;
}

export interface PublishOptions {
  headers?: Record<string, string>;
}

export interface SubscribeOptions {
  agent?: string;
  channel?: string;
  subject?: string;
  timeout?: number;
  signal?: AbortSignal;
}

/** One message seen by `mesh.tap()`: a wiretap on a subject pattern. */
export interface TapEvent {
  subject: string;
  /** Decoded JSON payload, or the raw text when the payload is not JSON. */
  payload: Json | string;
  /** True when the message carried `X-Mesh-Status: error` (the payload is the error envelope). */
  isError: boolean;
}

export interface TapOptions {
  signal?: AbortSignal;
}

/** `mesh-instances` bucket contents: instance id → agent names it serves (ADR-0016). */
export type InstancesSnapshot = Record<string, string[]>;

export interface InstancesWatchOptions {
  signal?: AbortSignal;
}

export interface CatalogFilter {
  channel?: string;
  tags?: string[];
  streaming?: boolean;
  invocable?: boolean;
}

/** Structural validator (Zod-compatible) for KV model helpers. */
export interface Validator<T> {
  parse(value: unknown): T;
}
