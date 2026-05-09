import { ensureConnection } from "./nats";

export interface DecodedEvent {
  subject: string;
  payload: unknown; // JSON-decoded if possible, else raw string
  raw: string; // raw text for fallback rendering
  receivedAt: number; // Date.now()
}

/**
 * Subscribe to a NATS subject pattern and stream decoded messages to onMessage.
 *
 * Returns a stop function that unsubscribes the underlying NATS subscription.
 * NATS wildcards: '*' matches one segment, '>' matches one or more segments.
 *
 * Example:
 *   const stop = await subscribeSubjects("mesh.action.>", (e) => console.log(e));
 *   // ... later ...
 *   stop();
 *
 * This is plain NATS subject pubsub via the shared wsconnect singleton from
 * ./nats.ts (per ADR-0056 / D-15: browser-direct nats.ws, no FastAPI bridge).
 * The KV / stream path is reserved for the catalog and fleet mirrors in
 * ./catalog.ts and ./fleet.ts; this file deliberately avoids that surface.
 */
export async function subscribeSubjects(
  pattern: string,
  onMessage: (event: DecodedEvent) => void,
): Promise<() => void> {
  const nc = await ensureConnection();
  const sub = nc.subscribe(pattern);

  let stopped = false;
  (async () => {
    try {
      for await (const msg of sub) {
        if (stopped) break;
        const raw = msg.string();
        let payload: unknown;
        try {
          payload = msg.json();
        } catch {
          payload = raw;
        }
        try {
          onMessage({
            subject: msg.subject,
            payload,
            raw,
            receivedAt: Date.now(),
          });
        } catch (e) {
          // Handler errors must not kill the iterator: log and keep going.
          console.warn("EventFeed onMessage handler threw", e);
        }
      }
    } catch (e) {
      // The async iterator can throw on connection close. Suppress noise after
      // an explicit stop() so unmount paths stay quiet.
      if (!stopped) {
        console.warn("subscribeSubjects iterator failed", e);
      }
    }
  })();

  return () => {
    stopped = true;
    sub.unsubscribe();
  };
}
