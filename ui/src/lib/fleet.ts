import { Kvm } from "@nats-io/kv";
import { jetstream } from "@nats-io/jetstream";
import { ensureConnection } from "./nats";

export type FleetMember = {
  instance_id: string;
  zone: string;
  fleet_type: string;
  coords: { x: number; y: number };
  state: string;
  current_assignment: string | null;
  last_updated: number; // unix seconds
};

// Reader-side liveness per D-10: now - last_updated < 3 s ⇒ live.
// Three missed 1 Hz heartbeats and the row goes stale.
export const LIVENESS_STALENESS_MS = 3_000;

// KV bucket "mesh-context", keys under prefix "wildfire.fleet.>". Values are
// JSON FleetMember records. Subject namespace alias: wildfire.fleet.>
export async function watchFleet(
  onUpdate: (members: Record<string, FleetMember>) => void,
): Promise<() => void> {
  const nc = await ensureConnection();
  const js = jetstream(nc);
  const kv = await new Kvm(js).open("mesh-context");
  const watcher = await kv.watch({ key: "wildfire.fleet.>" });
  const decoder = new TextDecoder();
  const members: Record<string, FleetMember> = {};
  let cancelled = false;
  (async () => {
    for await (const e of watcher) {
      if (cancelled) break;
      // KvEntry.operation is "PUT" | "DEL" | "PURGE" depending on package
      // version; treat anything that isn't a PUT-with-value as a removal.
      const op = (e as { operation?: string }).operation;
      if (op === "DEL" || op === "DELETE" || op === "PURGE") {
        delete members[e.key];
        onUpdate({ ...members });
        continue;
      }
      if (!e.value || e.value.length === 0) {
        delete members[e.key];
        onUpdate({ ...members });
        continue;
      }
      try {
        const m = JSON.parse(decoder.decode(e.value)) as FleetMember;
        members[e.key] = m;
        onUpdate({ ...members });
      } catch {
        // ignore malformed fleet payloads
      }
    }
  })();
  return () => {
    cancelled = true;
    watcher.stop();
  };
}

export function isLive(m: FleetMember, nowMs: number = Date.now()): boolean {
  return nowMs - m.last_updated * 1000 < LIVENESS_STALENESS_MS;
}
