import type { KV } from "@nats-io/kv";
import { NotFound } from "./errors.js";
import type { AgentContract, CatalogEntry, CatalogFilter } from "./types.js";

export const CATALOG_BUCKET = "mesh-catalog";
export const CATALOG_KEY = "catalog";
export const REGISTRY_BUCKET = "mesh-registry";

// The catalog/registry wire is produced by the OAM SDK (Python today) and is
// trusted to conform to the contract schema. Primitives are coerced defensively;
// nested JSON Schemas are passed through as opaque objects.
function coerceEntry(raw: Record<string, unknown>): CatalogEntry {
  return {
    name: String(raw["name"] ?? ""),
    description: String(raw["description"] ?? ""),
    version: String(raw["version"] ?? "0.1.0"),
    tags: Array.isArray(raw["tags"]) ? (raw["tags"] as string[]) : [],
    invocable: raw["invocable"] !== false,
    streaming: raw["streaming"] === true,
  };
}

/** Parse a `mesh-registry` JSON value into an `AgentContract`. */
export function parseContract(value: string): AgentContract {
  const raw = JSON.parse(value) as Record<string, unknown>;
  const caps = (raw["capabilities"] ?? {}) as Record<string, unknown>;
  const x = (raw["x-agentmesh"] ?? {}) as Record<string, unknown>;
  const skills = Array.isArray(raw["skills"]) ? (raw["skills"] as Array<Record<string, unknown>>) : [];
  const skill0 = skills[0] ?? {};

  return {
    name: String(raw["name"] ?? ""),
    description: String(raw["description"] ?? ""),
    version: String(raw["version"] ?? "0.1.0"),
    capabilities: caps,
    skills,
    subject: String(x["subject"] ?? ""),
    tags: Array.isArray(x["tags"]) ? (x["tags"] as string[]) : [],
    invocable: caps["invocable"] !== false,
    streaming: caps["streaming"] === true,
    inputSchema: skill0["inputSchema"] as Record<string, unknown> | undefined,
    outputSchema: skill0["outputSchema"] as Record<string, unknown> | undefined,
    chunkSchema: x["chunk_schema"] as Record<string, unknown> | undefined,
    registeredAt: x["registered_at"] as string | undefined,
  };
}

export function filterCatalog(entries: CatalogEntry[], f: CatalogFilter = {}): CatalogEntry[] {
  return entries.filter((e) => {
    if (f.channel !== undefined && !(e.name === f.channel || e.name.startsWith(f.channel + "."))) return false;
    if (f.tags && !f.tags.every((t) => e.tags.includes(t))) return false;
    if (f.streaming !== undefined && e.streaming !== f.streaming) return false;
    if (f.invocable !== undefined && e.invocable !== f.invocable) return false;
    return true;
  });
}

/**
 * Warm catalog cache: seeded once from KV then kept in sync via a KV watch on
 * the single `catalog` key. May be milliseconds stale (CAS catalog writes).
 */
export class Discovery {
  private cache = new Map<string, CatalogEntry>();
  private stopped = false;
  private iter?: { stop: () => void };

  constructor(
    private readonly catalogKv: KV,
    private readonly registryKv: KV,
  ) {}

  async seed(): Promise<void> {
    const entry = await this.catalogKv.get(CATALOG_KEY);
    if (entry && entry.operation === "PUT" && entry.value.length > 0) {
      this.replace(entry.string());
    }
  }

  startWatch(): void {
    if (this.stopped || this.iter) return;
    void (async () => {
      try {
        const iter = await this.catalogKv.watch({ key: CATALOG_KEY });
        this.iter = iter;
        if (this.stopped) {
          iter.stop();
          return;
        }
        for await (const e of iter) {
          if (this.stopped) break;
          if (e.operation === "PUT" && e.value.length > 0) {
            try {
              this.replace(e.string());
            } catch {
              /* ignore malformed catalog payloads */
            }
          }
        }
      } catch {
        /* swallow teardown races (draining/closed connection) and watch setup errors */
      }
    })();
  }

  private replace(json: string): void {
    const arr = JSON.parse(json) as Array<Record<string, unknown>>;
    this.cache.clear();
    for (const raw of arr) {
      const entry = coerceEntry(raw);
      if (entry.name) this.cache.set(entry.name, entry);
    }
  }

  /** Cached entry for a name, or undefined if unknown (cache may be stale). */
  cachedEntry(name: string): CatalogEntry | undefined {
    return this.cache.get(name);
  }

  catalog(filter: CatalogFilter = {}): CatalogEntry[] {
    return filterCatalog([...this.cache.values()], filter);
  }

  async contract(name: string): Promise<AgentContract> {
    let entry;
    try {
      entry = await this.registryKv.get(name);
    } catch {
      throw new NotFound(`Agent '${name}' not found`, { agent: name });
    }
    if (!entry || entry.operation !== "PUT" || entry.value.length === 0) {
      throw new NotFound(`Agent '${name}' not found`, { agent: name });
    }
    return parseContract(entry.string());
  }

  async discover(channel?: string): Promise<AgentContract[]> {
    const entries = this.catalog(channel !== undefined ? { channel } : {});
    const out: AgentContract[] = [];
    for (const e of entries) {
      try {
        out.push(await this.contract(e.name));
      } catch {
        /* skip entries whose contract fetch fails */
      }
    }
    return out;
  }

  stop(): void {
    this.stopped = true;
    this.iter?.stop();
  }
}
