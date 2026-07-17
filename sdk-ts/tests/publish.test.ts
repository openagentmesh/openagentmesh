import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { Msg, NatsConnection } from "@nats-io/nats-core";
import { AgentMesh, InvalidInput } from "../src/index.js";
import { startNatsServer, type NatsServer } from "./helpers/server.js";
import { ensureBuckets, rawConnect, Sim } from "./helpers/sim.js";

let server: NatsServer;
let raw: NatsConnection;
let sim: Sim;
let mesh: AgentMesh;

beforeAll(async () => {
  server = await startNatsServer();
  raw = await rawConnect(server.url);
  await ensureBuckets(raw);
  sim = new Sim(raw);
  mesh = await AgentMesh.connect({ servers: server.url });
});

afterAll(async () => {
  await mesh?.close();
  await sim?.drain();
  await raw?.close();
  await server?.stop();
});

const DEC = new TextDecoder();

// Wrapped in an object because a bare Promise<Msg> would be unwrapped by the
// caller's `await` before publish() ever ran, deadlocking the test.
async function captureOne(subject: string): Promise<{ msg: Promise<Msg> }> {
  let resolve!: (m: Msg) => void;
  const msg = new Promise<Msg>((r) => (resolve = r));
  await sim.captureSubject(subject, (_p, m) => resolve(m));
  return { msg };
}

describe("publish", () => {
  it("publishes an object as application/json with stamped headers", async () => {
    const { msg } = await captureOne("telemetry.uav.42");
    await mesh.publish("telemetry.uav.42", { x: 10, y: 4 });
    const m = await msg;
    expect(m.headers?.get("X-Mesh-Content-Type")).toBe("application/json");
    expect(m.headers?.get("X-Mesh-Instance-Id")).toBe(mesh.instanceId);
    expect(m.headers?.get("X-Mesh-Request-Id")).toMatch(/^[0-9a-f]{32}$/);
    expect(JSON.parse(DEC.decode(m.data))).toEqual({ x: 10, y: 4 });
  });

  it("publishes a string as text/plain", async () => {
    const { msg } = await captureOne("log.line");
    await mesh.publish("log.line", "hello");
    const m = await msg;
    expect(m.headers?.get("X-Mesh-Content-Type")).toBe("text/plain");
    expect(DEC.decode(m.data)).toBe("hello");
  });

  it("publishes bytes as application/octet-stream", async () => {
    const { msg } = await captureOne("blob.raw");
    await mesh.publish("blob.raw", new Uint8Array([1, 2, 3]));
    const m = await msg;
    expect(m.headers?.get("X-Mesh-Content-Type")).toBe("application/octet-stream");
    expect([...m.data]).toEqual([1, 2, 3]);
  });

  it("merges caller headers (caller wins)", async () => {
    const { msg } = await captureOne("trace.line");
    await mesh.publish("trace.line", { a: 1 }, { headers: { "X-Trace": "abc" } });
    const m = await msg;
    expect(m.headers?.get("X-Trace")).toBe("abc");
  });

  it("rejects subjects containing wildcards", async () => {
    await expect(mesh.publish("bad.*.subject", {})).rejects.toBeInstanceOf(InvalidInput);
    await expect(mesh.publish("bad.>", {})).rejects.toBeInstanceOf(InvalidInput);
  });
});
