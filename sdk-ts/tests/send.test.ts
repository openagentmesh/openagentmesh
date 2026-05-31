import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { Msg, NatsConnection } from "@nats-io/nats-core";
import { AgentMesh, HandlerError, InvalidInput, MeshTimeout } from "../src/index.js";
import { delay } from "./helpers/delay.js";
import { startNatsServer, type NatsServer } from "./helpers/server.js";
import { ensureBuckets, errorResult, rawConnect, Sim } from "./helpers/sim.js";

let server: NatsServer;
let raw: NatsConnection;
let sim: Sim;
let mesh: AgentMesh;

beforeAll(async () => {
  server = await startNatsServer();
  raw = await rawConnect(server.url);
  await ensureBuckets(raw);
  sim = new Sim(raw);

  sim.responder("billing.charge", (p: any) => ({ ack: true, amount: p.amount }));
  sim.responder("send.boom", () => errorResult("handler_error", "charge failed"));
  sim.capture("send.silent", () => {}); // never replies

  mesh = await AgentMesh.connect({ servers: server.url });
});

afterAll(async () => {
  await mesh?.close();
  await sim?.drain();
  await raw?.close();
  await server?.stop();
});

function once<T>(): { promise: Promise<T>; resolve: (v: T) => void } {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe("send", () => {
  it("fire-and-forget delivers the payload with stamped headers", async () => {
    const got = once<{ payload: any; m: Msg }>();
    sim.capture("audit.logger", (payload, m) => got.resolve({ payload, m }));
    await sim.ready();
    await mesh.send("audit.logger", { event: "login" });
    const { payload, m } = await got.promise;
    expect(payload).toEqual({ event: "login" });
    expect(m.headers?.get("X-Mesh-Instance-Id")).toBe(mesh.instanceId);
    expect(m.headers?.get("X-Mesh-Request-Id")).toMatch(/^[0-9a-f]{32}$/);
    expect(m.reply).toBeFalsy(); // no reply subject for fire-and-forget
  });

  it("managed onReply fires with the responder's payload", async () => {
    const got = once<any>();
    await mesh.send("billing.charge", { amount: 100 }, { onReply: (msg) => got.resolve(msg), timeout: 2000 });
    expect(await got.promise).toEqual({ ack: true, amount: 100 });
  });

  it("managed onError fires when the responder returns an error", async () => {
    const got = once<Error>();
    await mesh.send("send.boom", {}, { onReply: () => {}, onError: (e) => got.resolve(e), timeout: 2000 });
    expect(await got.promise).toBeInstanceOf(HandlerError);
  });

  it("managed onError fires on reply timeout", async () => {
    const got = once<Error>();
    await mesh.send("send.silent", {}, { onReply: () => {}, onError: (e) => got.resolve(e), timeout: 300 });
    expect(await got.promise).toBeInstanceOf(MeshTimeout);
  });

  it("manual replyTo stamps X-Mesh-Reply-To and the NATS reply subject", async () => {
    const got = once<Msg>();
    sim.capture("worker.task", (_p, m) => got.resolve(m));
    await sim.ready();
    await mesh.send("worker.task", { id: 7 }, { replyTo: "my.custom.inbox" });
    const m = await got.promise;
    expect(m.headers?.get("X-Mesh-Reply-To")).toBe("my.custom.inbox");
    expect(m.reply).toBe("my.custom.inbox");
  });

  it("rejects when onReply and replyTo are both provided", async () => {
    await expect(
      mesh.send("worker.task", {}, { onReply: () => {}, replyTo: "x" }),
    ).rejects.toBeInstanceOf(InvalidInput);
  });
});
