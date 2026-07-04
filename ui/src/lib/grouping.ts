import { CatalogEntry } from "./catalog";

// Registry grouping by channel prefix (ADR-0056 wave-3 amendment): agent
// names like "high-alt.uav" group under their channel; single-segment names
// ("fire-sim", "tasker") collect under Services. Group order is fixed so
// the registry reads top-down as the operational stack: air first, ground,
// then mesh-level services.
export type AgentGroup = {
  key: string;
  label: string;
  entries: CatalogEntry[];
};

const CHANNEL_ORDER = ["high-alt", "low-alt", "ground"];
const CHANNEL_LABELS: Record<string, string> = {
  "high-alt": "High altitude",
  "low-alt": "Low altitude",
  ground: "Ground",
};

export function groupCatalog(catalog: CatalogEntry[]): AgentGroup[] {
  const byKey = new Map<string, CatalogEntry[]>();
  for (const entry of catalog) {
    const dot = entry.name.indexOf(".");
    const key = dot > 0 ? entry.name.slice(0, dot) : "services";
    const list = byKey.get(key) ?? [];
    list.push(entry);
    byKey.set(key, list);
  }

  const groups: AgentGroup[] = [];
  for (const key of CHANNEL_ORDER) {
    const entries = byKey.get(key);
    if (entries) {
      groups.push({ key, label: CHANNEL_LABELS[key], entries: sorted(entries) });
      byKey.delete(key);
    }
  }
  // Unknown channels (future fleets) keep their prefix as the label.
  for (const [key, entries] of byKey) {
    if (key === "services") continue;
    groups.push({ key, label: key, entries: sorted(entries) });
  }
  const services = byKey.get("services");
  if (services) {
    groups.push({ key: "services", label: "Services", entries: sorted(services) });
  }
  return groups;
}

function sorted(entries: CatalogEntry[]): CatalogEntry[] {
  return [...entries].sort((a, b) => a.name.localeCompare(b.name));
}
