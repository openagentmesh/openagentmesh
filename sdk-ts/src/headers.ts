import { headers, type MsgHdrs } from "@nats-io/nats-core";

// Mesh header names — verified literal against the Python SDK.
export const H = {
  requestId: "X-Mesh-Request-Id",
  stream: "X-Mesh-Stream",
  replyTo: "X-Mesh-Reply-To",
  instanceId: "X-Mesh-Instance-Id",
  contentType: "X-Mesh-Content-Type",
  status: "X-Mesh-Status",
  source: "X-Mesh-Source",
  streamSeq: "X-Mesh-Stream-Seq",
  streamEnd: "X-Mesh-Stream-End",
} as const;

export const STATUS_OK = "ok";
export const STATUS_ERROR = "error";

export type HeaderInit = Record<string, string>;

/**
 * Build a NATS `MsgHdrs` from a plain object, stamping `X-Mesh-Instance-Id`
 * via setdefault semantics (a caller-supplied instance id wins). User headers
 * provided in `extra` are merged last and win over base entries.
 */
export function buildHeaders(
  base: HeaderInit,
  instanceId: string,
  extra?: HeaderInit,
): MsgHdrs {
  const h = headers();
  for (const [k, v] of Object.entries(base)) h.set(k, v);
  if (extra) for (const [k, v] of Object.entries(extra)) h.set(k, v);
  if (!h.has(H.instanceId)) h.set(H.instanceId, instanceId);
  return h;
}

/** Read a header value, returning `undefined` when absent. */
export function readHeader(h: MsgHdrs | undefined, key: string): string | undefined {
  if (!h || !h.has(key)) return undefined;
  return h.get(key);
}
