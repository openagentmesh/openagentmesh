import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { NatsConnection } from "@nats-io/nats-core";
import { AgentMesh, ConnectionFailed } from "../src/index.js";
import { startNatsServer, type NatsServer } from "./helpers/server.js";
import { ensureBuckets, rawConnect } from "./helpers/sim.js";

let server: NatsServer;
let raw: NatsConnection;

beforeAll(async () => {
  server = await startNatsServer();
  raw = await rawConnect(server.url);
  await ensureBuckets(raw);
});

afterAll(async () => {
  await raw?.close();
  await server?.stop();
});

describe("connect", () => {
  it("connects over nats:// (node tcp) with a uuid-hex instanceId", async () => {
    const mesh = await AgentMesh.connect({ servers: server.url });
    expect(mesh.instanceId).toMatch(/^[0-9a-f]{32}$/);
    await mesh.close();
  });

  it("instanceId is stable for the connection lifetime", async () => {
    const mesh = await AgentMesh.connect({ servers: server.url });
    const first = mesh.instanceId;
    expect(mesh.instanceId).toBe(first);
    await mesh.close();
  });

  it("distinct connections get distinct instance ids", async () => {
    const a = await AgentMesh.connect({ servers: server.url });
    const b = await AgentMesh.connect({ servers: server.url });
    expect(a.instanceId).not.toBe(b.instanceId);
    await a.close();
    await b.close();
  });

  it("rejects with ConnectionFailed when no servers/configUrl given", async () => {
    await expect(AgentMesh.connect({})).rejects.toBeInstanceOf(ConnectionFailed);
  });
});
