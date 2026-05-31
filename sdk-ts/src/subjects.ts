// Subject scheme — verified literal against the Python SDK (`_subjects.py`).
// All message-layer subjects use the `mesh.*` prefix; there is no `oam.*` alias.

/** Dotted-name / publish-subject validity. No wildcards (`*`, `>`) allowed. */
export const SUBJECT_RE = /^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)*$/;

/** `mesh.agent.{name}` — invocation subject for call/stream/send. */
export function computeSubject(name: string): string {
  return `mesh.agent.${name}`;
}

/** `mesh.agent.{name}.events` — a single publisher's event subject. */
export function computeEventSubject(name: string): string {
  return `mesh.agent.${name}.events`;
}

/** `mesh.errors.{name}` — dead-letter / error observability subject. */
export function computeErrorSubject(name: string): string {
  return `mesh.errors.${name}`;
}

/** `mesh.agent.{channel}.>` — wildcard subscribe across a dotted channel prefix. */
export function channelSubject(channel: string): string {
  return `mesh.agent.${channel}.>`;
}

/** `mesh.stream.{requestId}` — per-request streaming chunk subject. */
export function streamSubject(requestId: string): string {
  return `mesh.stream.${requestId}`;
}

/** `mesh.results.{requestId}` — managed-callback reply subject for send(). */
export function resultsSubject(requestId: string): string {
  return `mesh.results.${requestId}`;
}

/** uuid4 hex (32 lowercase hex chars, no dashes) — matches Python `uuid4().hex`. */
export function newRequestId(): string {
  return globalThis.crypto.randomUUID().replace(/-/g, "");
}

export function isValidSubject(subject: string): boolean {
  return SUBJECT_RE.test(subject);
}
