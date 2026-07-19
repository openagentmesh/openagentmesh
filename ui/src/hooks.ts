import { useEffect, useState } from "react";
import type { AgentContract, CatalogEntry } from "@openagentmesh/sdk";
import { useMesh } from "./MeshProvider";

const DEATH_PATTERN = "mesh.death.>";

/**
 * Live agent names, from the `mesh-instances` KV watch (authoritative) plus
 * `mesh.death.>` notices (instant offline transitions before KV catches up).
 * Null until the first instances snapshot arrives; stays null on pre-liveness
 * meshes (no bucket), which hides the status dots entirely.
 */
export function useLiveness(): Set<string> | null {
  const { mesh } = useMesh();
  const [live, setLive] = useState<Set<string> | null>(null);

  useEffect(() => {
    if (!mesh) return;
    const abort = new AbortController();

    void (async () => {
      try {
        for await (const snapshot of mesh.instancesWatch({ signal: abort.signal })) {
          const agents = new Set(Object.values(snapshot).flat());
          setLive(agents);
        }
      } catch {
        /* aborted on unmount, or the watch failed — keep the last state */
      }
    })();

    void (async () => {
      try {
        for await (const event of mesh.tap(DEATH_PATTERN, { signal: abort.signal })) {
          const name = event.subject.slice("mesh.death.".length);
          if (!name) continue;
          setLive((prev) => {
            if (!prev || !prev.has(name)) return prev;
            const next = new Set(prev);
            next.delete(name);
            return next;
          });
        }
      } catch {
        /* aborted on unmount */
      }
    })();

    return () => abort.abort();
  }, [mesh]);

  return live;
}

/**
 * The SDK keeps its catalog cache warm via a KV watch on the single
 * `catalog` key (ADR-0014); polling the in-memory cache is how the table
 * tracks registrations without a second wire subscription.
 */
const CATALOG_POLL_MS = 2000;

/** Catalog rows sorted by name; null while the first load is in flight. */
export function useCatalog(): CatalogEntry[] | null {
  const { mesh } = useMesh();
  const [entries, setEntries] = useState<CatalogEntry[] | null>(null);

  useEffect(() => {
    if (!mesh) return;
    let cancelled = false;
    const refresh = () => {
      mesh
        .catalog()
        .then((rows) => {
          if (!cancelled) setEntries([...rows].sort((a, b) => a.name.localeCompare(b.name)));
        })
        .catch(() => {
          /* transient discovery failure — keep the last snapshot */
        });
    };
    refresh();
    const timer = setInterval(refresh, CATALOG_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [mesh]);

  return entries;
}

export interface ContractState {
  contract: AgentContract | null;
  error: string | null;
}

/** Full contract from the mesh-registry bucket; error carries NotFound etc. */
export function useContract(name: string): ContractState {
  const { mesh } = useMesh();
  const [state, setState] = useState<ContractState>({ contract: null, error: null });

  useEffect(() => {
    if (!mesh) return;
    let cancelled = false;
    setState({ contract: null, error: null });
    mesh
      .contract(name)
      .then((contract) => {
        if (!cancelled) setState({ contract, error: null });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({ contract: null, error: err instanceof Error ? err.message : String(err) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mesh, name]);

  return state;
}
