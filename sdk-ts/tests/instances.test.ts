import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Kvm } from "@nats-io/kv";
import type { NatsConnection } from "@nats-io/nats-core";
import { AgentMesh } from "../src/index.js";
import type { InstancesSnapshot } from "../src/index.js";
import { startNatsServer, type NatsServer } from "./helpers/server.js";
import { ensureBuckets, rawConnect } from "./helpers/sim.js";

let server: NatsServer;
let raw: NatsConnection;
let mesh: AgentMesh;

const ENC = new TextEncoder();

async function putInstance(nc: NatsConnection, instanceId: string, agents: string[]): Promise<void> {
  const kv = await new Kvm(nc).open("mesh-instances");
  await kv.put(instanceId, ENC.encode(JSON.stringify({ agents })));
}

async function delInstance(nc: NatsConnection, instanceId: string): Promise<void> {
  const kv = await new Kvm(nc).open("mesh-instances");
  await kv.delete(instanceId);
}

/** Pull snapshots until `pred` matches (the watch coalesces are timing-dependent). */
async function nextMatching(
  iter: AsyncIterator<InstancesSnapshot>,
  pred: (s: InstancesSnapshot) => boolean,
): Promise<InstancesSnapshot> {
  for (let i = 0; i < 20; i++) {
    const res = await iter.next();
    if (res.done) throw new Error("instancesWatch ended before a matching snapshot");
    if (pred(res.value)) return res.value;
  }
  throw new Error("no matching snapshot after 20 yields");
}

beforeAll(async () => {
  server = await startNatsServer();
  raw = await rawConnect(server.url);
  await ensureBuckets(raw);
  mesh = await AgentMesh.connect({ servers: server.url });
});

afterAll(async () => {
  await mesh?.close();
  await raw?.close();
  await server?.stop();
});

describe("instancesWatch", () => {
  it("completes without yielding when the mesh-instances bucket is absent", async () => {
    // Runs first: `ensureBuckets` does not create mesh-instances, so the
    // bucket only exists once a later test creates it.
    const iter = mesh.instancesWatch()[Symbol.asyncIterator]();
    const res = await iter.next();
    expect(res.done).toBe(true);
  });

  it("yields a snapshot containing existing records, then updates on put/delete", async () => {
    await new Kvm(raw).create("mesh-instances", { history: 5 });
    await putInstance(raw, "host-1", ["translator", "ticker"]);

    const abort = new AbortController();
    const iter = mesh.instancesWatch({ signal: abort.signal })[Symbol.asyncIterator]();

    const withHost1 = await nextMatching(iter, (s) => "host-1" in s);
    expect(withHost1["host-1"]).toEqual(["translator", "ticker"]);

    await putInstance(raw, "host-2", ["reindexer"]);
    const withHost2 = await nextMatching(iter, (s) => "host-2" in s);
    expect(withHost2["host-2"]).toEqual(["reindexer"]);
    expect(withHost2["host-1"]).toEqual(["translator", "ticker"]);

    await delInstance(raw, "host-1");
    const afterDel = await nextMatching(iter, (s) => !("host-1" in s));
    expect(afterDel["host-2"]).toEqual(["reindexer"]);

    abort.abort();
  });
});
