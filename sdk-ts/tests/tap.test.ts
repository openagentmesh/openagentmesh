import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { NatsConnection } from "@nats-io/nats-core";
import { AbortError, AgentMesh } from "../src/index.js";
import type { TapEvent } from "../src/index.js";
import { delay } from "./helpers/delay.js";
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

describe("tap", () => {
  it("yields subject + decoded JSON payload for every message on a wildcard", async () => {
    const iter = mesh.tap("taproot.>")[Symbol.asyncIterator]();
    const p1 = iter.next();
    await delay(150);
    await sim.emitSubject("taproot.alpha", { n: 1 });
    const e1 = (await p1).value as TapEvent;
    expect(e1.subject).toBe("taproot.alpha");
    expect(e1.payload).toEqual({ n: 1 });
    expect(e1.isError).toBe(false);

    const p2 = iter.next();
    await sim.emitSubject("taproot.beta.gamma", { n: 2 });
    const e2 = (await p2).value as TapEvent;
    expect(e2.subject).toBe("taproot.beta.gamma");
    expect(e2.payload).toEqual({ n: 2 });
  });

  it("yields non-JSON payloads as raw text", async () => {
    const iter = mesh.tap("tapraw.feed")[Symbol.asyncIterator]();
    const p = iter.next();
    await delay(150);
    raw.publish("tapraw.feed", new TextEncoder().encode("plain text, not json"));
    const e = (await p).value as TapEvent;
    expect(e.payload).toBe("plain text, not json");
  });

  it("flags error-envelope messages instead of throwing", async () => {
    const iter = mesh.tap("taperr.feed")[Symbol.asyncIterator]();
    const p = iter.next();
    await delay(150);
    await sim.emitError("taperr.feed", { code: "handler_error", message: "boom" });
    const e = (await p).value as TapEvent;
    expect(e.isError).toBe(true);
    expect(e.payload).toMatchObject({ code: "handler_error", message: "boom" });
  });

  it("keeps iterating past X-Mesh-Stream-End (a feed never self-terminates)", async () => {
    const iter = mesh.tap("tapend.feed")[Symbol.asyncIterator]();
    const p1 = iter.next();
    await delay(150);
    await sim.emitSubject("tapend.feed", { last: true }, { end: true });
    expect(((await p1).value as TapEvent).payload).toEqual({ last: true });

    const p2 = iter.next();
    await sim.emitSubject("tapend.feed", { after: "end" });
    expect(((await p2).value as TapEvent).payload).toEqual({ after: "end" });
  });

  it("rejects the pending next() with AbortError when the signal aborts", async () => {
    const abort = new AbortController();
    const iter = mesh.tap("tapabort.feed", { signal: abort.signal })[Symbol.asyncIterator]();
    const p = iter.next();
    await delay(50);
    abort.abort();
    await expect(p).rejects.toBeInstanceOf(AbortError);
  });
});
