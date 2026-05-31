// Payload codec. The OAM wire convention is UTF-8 JSON for structured payloads.
// NATS v3 payloads are `string | Uint8Array`; we always encode to bytes.

const ENC = new TextEncoder();
const DEC = new TextDecoder();

/** Encode a value as UTF-8 JSON bytes. `undefined`/`null` → empty bytes. */
export function encodeJSON(value: unknown): Uint8Array {
  if (value === undefined || value === null) return new Uint8Array(0);
  return ENC.encode(JSON.stringify(value));
}

/**
 * Decode UTF-8 JSON bytes into an object. An empty body decodes to `{}`
 * (mirrors the Python client, where an empty reply body is treated as `{}`).
 *
 * This is unvalidated deserialization: the parsed value is cast to `T` without
 * runtime shape checking. The SDK is schema-agnostic by design; validate with a
 * structural validator (e.g. `mesh.kv.getModel(key, schema)` or Zod) when you
 * need runtime guarantees.
 */
export function decodeJSON<T = Record<string, unknown>>(data: Uint8Array): T {
  if (!data || data.length === 0) return {} as T;
  const text = DEC.decode(data);
  if (text.trim() === "") return {} as T;
  return JSON.parse(text) as T;
}

export function encodeText(s: string): Uint8Array {
  return ENC.encode(s);
}

export function decodeText(data: Uint8Array): string {
  return DEC.decode(data);
}
