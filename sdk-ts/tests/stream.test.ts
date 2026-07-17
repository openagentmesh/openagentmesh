import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { NatsConnection } from "@nats-io/nats-core";
import { AgentMesh, ChunkSequenceError, HandlerError, MeshTimeout } from "../src/index.js";
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

  await sim.streamer("nlp.summarizer", () => [{ token: "a" }, { token: "b" }, { token: "c" }]);
  await sim.streamerError("flaky.stream", [{ token: "a" }], { code: "handler_error", message: "mid-stream boom" });
  await sim.streamerBadSeq("gap.stream", [{ token: "a" }, { token: "b" }]);
  await sim.capture("stream.silent", () => {}); // receives stream request, never emits chunks

  mesh = await AgentMesh.connect({ servers: server.url });
});

afterAll(async () => {
  await mesh?.close();
  await sim?.drain();
  await raw?.close();
  await server?.stop();
});

describe("stream", () => {
  it("yields chunks in order until the end marker", async () => {
    const got: unknown[] = [];
    for await (const c of mesh.stream("nlp.summarizer", { url: "x" })) got.push(c);
    expect(got).toEqual([{ token: "a" }, { token: "b" }, { token: "c" }]);
  });

  it("throws the typed error when the stream errors mid-flight", async () => {
    const got: unknown[] = [];
    await expect(async () => {
      for await (const c of mesh.stream("flaky.stream", {})) got.push(c);
    }).rejects.toBeInstanceOf(HandlerError);
    expect(got).toEqual([{ token: "a" }]); // the good chunk arrived first
  });

  it("throws ChunkSequenceError on an out-of-order sequence", async () => {
    await expect(async () => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      for await (const _c of mesh.stream("gap.stream", {})) {
        /* consume */
      }
    }).rejects.toBeInstanceOf(ChunkSequenceError);
  });

  it("times out when no chunks arrive", async () => {
    await expect(async () => {
      for await (const _c of mesh.stream("stream.silent", {}, { timeout: 300 })) {
        /* none */
      }
    }).rejects.toBeInstanceOf(MeshTimeout);
  });

  it("can be cancelled via AbortSignal", async () => {
    const ac = new AbortController();
    const got: unknown[] = [];
    const run = (async () => {
      for await (const c of mesh.stream("nlp.summarizer", {}, { signal: ac.signal })) {
        got.push(c);
        ac.abort();
      }
    })();
    await expect(run).rejects.toThrow();
    expect(got.length).toBeGreaterThanOrEqual(1);
  });
});
