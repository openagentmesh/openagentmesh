import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { Msg, NatsConnection } from "@nats-io/nats-core";
import { AgentMesh, HandlerError, MeshTimeout, NotAvailable, NotFound } from "../src/index.js";
import { startNatsServer, type NatsServer } from "./helpers/server.js";
import { ensureBuckets, errorResult, rawConnect, seedCatalog, Sim } from "./helpers/sim.js";

let server: NatsServer;
let raw: NatsConnection;
let sim: Sim;
let mesh: AgentMesh;

beforeAll(async () => {
  server = await startNatsServer();
  raw = await rawConnect(server.url);
  await ensureBuckets(raw);
  sim = new Sim(raw);

  await sim.responder("finance.risk.scorer", (payload: any) => ({ score: 0.9, applicant: payload.applicant }));
  await sim.responder("boom", () => errorResult("handler_error", "kaboom"));
  await sim.capture("silent", () => {}); // receives but never replies → timeout

  mesh = await AgentMesh.connect({ servers: server.url });
});

afterAll(async () => {
  await mesh?.close();
  await sim?.drain();
  await raw?.close();
  await server?.stop();
});

describe("call", () => {
  it("returns the responder's reply payload", async () => {
    const out = await mesh.call("finance.risk.scorer", { applicant: "A-1023" });
    expect(out).toEqual({ score: 0.9, applicant: "A-1023" });
  });

  it("stamps X-Mesh-Request-Id (uuid hex) and X-Mesh-Instance-Id on the request", async () => {
    let seen: Msg | undefined;
    await sim.responder("echo.headers", (_p, m: Msg) => {
      seen = m;
      return { ok: true };
    });
    await mesh.call("echo.headers", {});
    expect(seen?.headers?.get("X-Mesh-Request-Id")).toMatch(/^[0-9a-f]{32}$/);
    expect(seen?.headers?.get("X-Mesh-Instance-Id")).toBe(mesh.instanceId);
    expect(seen?.headers?.get("X-Mesh-Stream")).toBe(""); // not a stream request
  });

  it("maps an X-Mesh-Status: error reply to the typed error", async () => {
    await expect(mesh.call("boom", {})).rejects.toBeInstanceOf(HandlerError);
  });

  it("throws NotFound when no agent serves the subject", async () => {
    await expect(mesh.call("nobody.home", {})).rejects.toBeInstanceOf(NotFound);
  });

  it("throws NotAvailable when the agent is cataloged but nothing serves it (ADR-0055)", async () => {
    // A lifecycle-gated agent stays in the catalog while its gate is closed;
    // no-responders then means "offline", not "missing".
    await seedCatalog(raw, [
      { name: "gated", description: "gated agent", version: "1.0.0", invocable: true, streaming: false },
    ]);
    for (let i = 0; i < 100; i++) {
      const rows = await mesh.catalog();
      if (rows.some((e) => e.name === "gated")) break;
      await new Promise((r) => setTimeout(r, 20));
    }
    const err = await mesh.call("gated", {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(NotAvailable);
    expect((err as NotAvailable).code).toBe("not_available");
    expect((err as NotAvailable).agent).toBe("gated");
  });

  it("throws MeshTimeout when the agent never replies", async () => {
    await expect(mesh.call("silent", {}, { timeout: 300 })).rejects.toBeInstanceOf(MeshTimeout);
  });
});
