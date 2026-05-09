import { Kvm } from "@nats-io/kv";
import { jetstream } from "@nats-io/jetstream";
import { ensureConnection } from "./nats";

export type CatalogEntry = {
  name: string;
  description: string;
  version: string;
  tags: string[];
  invocable: boolean;
  streaming: boolean;
};

// KV bucket "mesh-catalog", key "catalog" — the value is a JSON array of
// CatalogEntry. Subject namespace alias: oam.catalog.>
export async function watchCatalog(
  onUpdate: (entries: CatalogEntry[]) => void,
): Promise<() => void> {
  const nc = await ensureConnection();
  const js = jetstream(nc);
  const kv = await new Kvm(js).open("mesh-catalog");
  const watcher = await kv.watch({ key: "catalog" });
  const decoder = new TextDecoder();
  let cancelled = false;
  (async () => {
    for await (const e of watcher) {
      if (cancelled) break;
      if (!e.value || e.value.length === 0) continue;
      try {
        const arr = JSON.parse(decoder.decode(e.value)) as CatalogEntry[];
        onUpdate(arr);
      } catch {
        // ignore malformed catalog payloads
      }
    }
  })();
  return () => {
    cancelled = true;
    watcher.stop();
  };
}
