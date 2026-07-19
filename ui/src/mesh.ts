import { AgentMesh } from "@openagentmesh/sdk";
import type { AgentContract, CatalogEntry } from "@openagentmesh/sdk";

/**
 * The slice of the SDK surface the UI consumes. Production wraps a connected
 * `AgentMesh` (which satisfies this structurally); tests inject a fake via
 * `<MeshProvider client={...}>`.
 */
export interface MeshClient {
  catalog(): Promise<CatalogEntry[]>;
  contract(name: string): Promise<AgentContract>;
  close(): Promise<void>;
}

/** Bootstrap per ADR-0056: fetch `/config.json`, connect to its websocket URL. */
export async function connectMesh(configUrl = "/config.json"): Promise<MeshClient> {
  return AgentMesh.connect({ configUrl, name: "oam-admin-ui" });
}
