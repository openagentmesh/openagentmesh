import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { NatsConnection } from "@nats-io/nats-core";
import { AgentMesh, KVKeyExists, NotFound } from "../src/index.js";
import { delay } from "./helpers/delay.js";
import { startNatsServer, type NatsServer } from "./helpers/server.js";
import { ensureBuckets, putContext, rawConnect } from "./helpers/sim.js";

let server: NatsServer;
let raw: NatsConnection;
let mesh: AgentMesh;

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

describe("kv (mesh-context)", () => {
  it("put then get round-trips a JSON value", async () => {
    await mesh.kv.put("wildfire.fire.state", { burning: 3 });
    expect(JSON.parse(await mesh.kv.get("wildfire.fire.state"))).toEqual({ burning: 3 });
  });

  it("get throws NotFound for a missing key", async () => {
    await expect(mesh.kv.get("nope.missing")).rejects.toBeInstanceOf(NotFound);
  });

  it("list returns a prefix snapshot", async () => {
    await putContext(raw, "fleet.a", { id: "a" });
    await putContext(raw, "fleet.b", { id: "b" });
    const rows = await mesh.kv.list("fleet.*");
    expect(rows.map((r) => r.key).sort()).toEqual(["fleet.a", "fleet.b"]);
    expect(rows.every((r) => r.operation === "PUT")).toBe(true);
  });

  it("create is put-if-absent and throws KVKeyExists on a duplicate", async () => {
    await mesh.kv.create("once.only", { v: 1 });
    await expect(mesh.kv.create("once.only", { v: 2 })).rejects.toBeInstanceOf(KVKeyExists);
  });

  it("update applies a CAS-retried mutation", async () => {
    await mesh.kv.put("counter", "0");
    await mesh.kv.update("counter", (cur) => String(Number(cur || "0") + 1));
    await mesh.kv.update("counter", (cur) => String(Number(cur || "0") + 1));
    expect(await mesh.kv.get("counter")).toBe("2");
  });

  it("update resurrects a deleted key via CAS revision 0", async () => {
    await mesh.kv.put("resurrect.me", "v1");
    await mesh.kv.delete("resurrect.me");
    await mesh.kv.update("resurrect.me", (cur) => (cur === "" ? "reborn" : `${cur}!`));
    expect(await mesh.kv.get("resurrect.me")).toBe("reborn");
  });

  it("watch yields decoded values on each PUT", async () => {
    const iter = mesh.kv.watch("watched.key")[Symbol.asyncIterator]();
    const first = iter.next();
    await delay(150);
    await putContext(raw, "watched.key", { n: 1 });
    expect(JSON.parse((await first).value as string)).toEqual({ n: 1 });
  });

  it("watchEntries reports PUT then DELETE (normalized)", async () => {
    const seen: Array<{ op: string; key: string; value: string | null }> = [];
    const stop = mesh.kv.watchEntries("member.*", (e) => seen.push({ op: e.operation, key: e.key, value: e.value }));
    await delay(150);
    await putContext(raw, "member.x", { online: true });
    await delay(150);
    const kvm = (await import("@nats-io/kv")).Kvm;
    const ctx = await new kvm(raw).open("mesh-context");
    await ctx.delete("member.x");
    await delay(200);
    stop();
    expect(seen.some((s) => s.op === "PUT" && s.key === "member.x")).toBe(true);
    expect(seen.some((s) => s.op === "DELETE" && s.key === "member.x" && s.value === null)).toBe(true);
  });

  it("getModel validates with a structural validator", async () => {
    const validator = {
      parse(v: unknown) {
        const o = v as { burning: number };
        if (typeof o.burning !== "number") throw new Error("bad");
        return o;
      },
    };
    await mesh.kv.putModel("fire.model", { burning: 7 });
    const m = await mesh.kv.getModel("fire.model", validator);
    expect(m.burning).toBe(7);
  });
});
