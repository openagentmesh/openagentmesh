import { wsconnect, type NatsConnection } from "@nats-io/nats-core";
import { ConnectionFailed } from "./errors.js";
import type { ConnectOptions } from "./types.js";

function isWsUrl(u: string): boolean {
  return u.startsWith("ws://") || u.startsWith("wss://");
}

/**
 * Open a NATS connection, choosing the transport from the server URL scheme:
 * `ws://`/`wss://` → `wsconnect` (browser/WebSocket); `nats://`/`tls://` → the
 * Node TCP transport (`@nats-io/transport-node`, dynamically imported so the
 * browser build never pulls it in).
 */
export async function openConnection(opts: ConnectOptions): Promise<NatsConnection> {
  let servers = opts.servers;

  if (opts.configUrl) {
    const res = await fetch(opts.configUrl);
    const cfg = (await res.json()) as { nats_ws_url: string };
    servers = cfg.nats_ws_url;
  }

  if (!servers) {
    throw new ConnectionFailed("AgentMesh.connect requires `servers` or `configUrl`");
  }

  const list = Array.isArray(servers) ? servers : [servers];
  const useWs = list.some(isWsUrl);
  const name = opts.name;

  try {
    if (useWs) {
      return await wsconnect({ servers: list, ...(name ? { name } : {}) });
    }
    const mod = await import("@nats-io/transport-node");
    return await mod.connect({ servers: list, ...(name ? { name } : {}) });
  } catch (err) {
    throw new ConnectionFailed(`failed to connect to NATS: ${(err as Error).message}`);
  }
}
