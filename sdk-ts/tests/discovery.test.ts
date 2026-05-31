import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { NatsConnection } from "@nats-io/nats-core";
import { AgentMesh, NotFound } from "../src/index.js";
import { delay } from "./helpers/delay.js";
import { startNatsServer, type NatsServer } from "./helpers/server.js";
import { ensureBuckets, rawConnect, seedCatalog, seedContract } from "./helpers/sim.js";

let server: NatsServer;
let raw: NatsConnection;
let mesh: AgentMesh;

const CATALOG = [
  { name: "finance.risk.scorer", description: "scores risk", version: "1.0.0", tags: ["pii", "finance"], invocable: true, streaming: false },
  { name: "finance.fx", description: "fx rates", version: "0.2.0", tags: ["finance"], invocable: true, streaming: false },
  { name: "nlp.summarizer", description: "summarizes", version: "0.1.0", tags: ["nlp"], invocable: true, streaming: true },
];

const CONTRACT = {
  name: "finance.risk.scorer",
  description: "scores risk",
  version: "1.0.0",
  capabilities: { streaming: false, invocable: true },
  skills: [
    {
      id: "finance.risk.scorer",
      name: "finance.risk.scorer",
      description: "scores risk",
      tags: ["pii", "finance"],
      inputSchema: { type: "object", properties: { applicant: { type: "string" } } },
      outputSchema: { type: "object", properties: { score: { type: "number" } } },
    },
  ],
  "x-agentmesh": { subject: "mesh.agent.finance.risk.scorer", tags: ["pii", "finance"], registered_at: "2026-05-31T00:00:00Z" },
};

beforeAll(async () => {
  server = await startNatsServer();
  raw = await rawConnect(server.url);
  await ensureBuckets(raw);
  await seedCatalog(raw, CATALOG);
  await seedContract(raw, "finance.risk.scorer", CONTRACT);
  mesh = await AgentMesh.connect({ servers: server.url });
});

afterAll(async () => {
  await mesh?.close();
  await raw?.close();
  await server?.stop();
});

describe("discovery", () => {
  it("catalog() returns all seeded entries from the warm cache", async () => {
    const all = await mesh.catalog();
    expect(all.map((e) => e.name).sort()).toEqual(["finance.fx", "finance.risk.scorer", "nlp.summarizer"]);
  });

  it("filters by channel prefix", async () => {
    const fin = await mesh.catalog({ channel: "finance" });
    expect(fin.map((e) => e.name).sort()).toEqual(["finance.fx", "finance.risk.scorer"]);
  });

  it("filters by tags (subset) and streaming flag", async () => {
    expect((await mesh.catalog({ tags: ["pii"] })).map((e) => e.name)).toEqual(["finance.risk.scorer"]);
    expect((await mesh.catalog({ streaming: true })).map((e) => e.name)).toEqual(["nlp.summarizer"]);
  });

  it("contract() returns a full AgentContract with schemas from skills[0]", async () => {
    const c = await mesh.contract("finance.risk.scorer");
    expect(c.name).toBe("finance.risk.scorer");
    expect(c.invocable).toBe(true);
    expect(c.streaming).toBe(false);
    expect(c.subject).toBe("mesh.agent.finance.risk.scorer");
    expect(c.inputSchema).toMatchObject({ type: "object" });
    expect(c.outputSchema).toMatchObject({ properties: { score: { type: "number" } } });
    expect(c.registeredAt).toBe("2026-05-31T00:00:00Z");
  });

  it("contract() throws NotFound for an unknown agent", async () => {
    await expect(mesh.contract("does.not.exist")).rejects.toBeInstanceOf(NotFound);
  });

  it("discover(channel) returns contracts for matching agents", async () => {
    const found = await mesh.discover({ channel: "finance.risk" });
    expect(found.map((c) => c.name)).toEqual(["finance.risk.scorer"]);
  });

  it("reflects live catalog updates via the KV watch", async () => {
    await seedCatalog(raw, [
      ...CATALOG,
      { name: "ops.pager", description: "pages on call", version: "0.1.0", tags: ["ops"], invocable: true, streaming: false },
    ]);
    await delay(300);
    const names = (await mesh.catalog()).map((e) => e.name);
    expect(names).toContain("ops.pager");
  });
});
