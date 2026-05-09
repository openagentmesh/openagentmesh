import { wsconnect, NatsConnection } from "@nats-io/nats-core";

let _nc: NatsConnection | null = null;

export async function ensureConnection(): Promise<NatsConnection> {
  if (_nc) return _nc;
  // /config.json is served by oam ui (default port 8088). It returns the
  // BROWSER's NATS WebSocket URL (default ws://127.0.0.1:4223), which is
  // distinct from the oam ui HTTP port.
  //
  // We use wsconnect from @nats-io/nats-core (v3 ecosystem). The legacy
  // nats.ws package is deprecated and its NatsConnection type is incompatible
  // with @nats-io/{kv,jetstream}@3.x.
  const cfgRes = await fetch("/config.json");
  const cfg = (await cfgRes.json()) as { nats_ws_url: string };
  _nc = await wsconnect({ servers: [cfg.nats_ws_url] });
  return _nc;
}
