import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { NatsConnection } from "@nats-io/nats-core";
import { AgentMesh, MeshTimeout } from "../src/index.js";
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

describe("subscribe", () => {
  it("receives a single agent's events (mesh.agent.{name}.events)", async () => {
    const iter = mesh.subscribe({ agent: "weather.station", timeout: 2000 })[Symbol.asyncIterator]();
    const p = iter.next();
    await delay(150);
    await sim.emitEvent("weather.station", { temp: 21 });
    const { value } = await p;
    expect(value).toEqual({ temp: 21 });
  });

  it("receives all agents under a channel (mesh.agent.{channel}.>)", async () => {
    const iter = mesh.subscribe({ channel: "wildfire.fleet", timeout: 2000 })[Symbol.asyncIterator]();
    const p = iter.next();
    await delay(150);
    await sim.emitEvent("wildfire.fleet.drone1", { alt: 120 });
    const { value } = await p;
    expect(value).toEqual({ alt: 120 });
  });

  it("subscribes to an explicit subject verbatim", async () => {
    const iter = mesh.subscribe({ subject: "custom.feed", timeout: 2000 })[Symbol.asyncIterator]();
    const p = iter.next();
    await delay(150);
    await sim.emitSubject("custom.feed", { hello: "world" });
    const { value } = await p;
    expect(value).toEqual({ hello: "world" });
  });

  it("terminates the iterator on X-Mesh-Stream-End: true", async () => {
    const got: unknown[] = [];
    const run = (async () => {
      for await (const evt of mesh.subscribe({ subject: "ending.feed", timeout: 2000 })) got.push(evt);
    })();
    await delay(150);
    await sim.emitSubject("ending.feed", { last: true }, { end: true });
    await run;
    expect(got).toEqual([{ last: true }]);
  });

  it("times out when no event arrives", async () => {
    await expect(async () => {
      for await (const _e of mesh.subscribe({ subject: "quiet.feed", timeout: 300 })) {
        /* none */
      }
    }).rejects.toBeInstanceOf(MeshTimeout);
  });

  it("rejects when agent and subject are both given", async () => {
    await expect(async () => {
      for await (const _e of mesh.subscribe({ agent: "a", subject: "s" })) {
        /* none */
      }
    }).rejects.toBeInstanceOf(Error);
  });
});
