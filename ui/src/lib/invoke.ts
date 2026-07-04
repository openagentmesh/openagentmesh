import { headers as natsHeaders } from "@nats-io/nats-core";
import { ensureConnection } from "./nats";

// Browser-side mesh.call: NATS request/reply on mesh.agent.{name} with a
// JSON body. Mirrors openagentmesh._invocation.InvocationMixin.call: the
// reply carries X-Mesh-Status: error + an error envelope on failure,
// otherwise a JSON payload.
export type MeshCallError = {
  code: string;
  message: string;
  agent: string;
  details?: Record<string, unknown>;
};

export type MeshCallResult =
  | { ok: true; payload: unknown; elapsedMs: number }
  | { ok: false; error: MeshCallError; elapsedMs: number };

function requestId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function callAgent(
  name: string,
  payload: unknown,
  timeoutMs = 30_000,
): Promise<MeshCallResult> {
  const nc = await ensureConnection();
  const h = natsHeaders();
  h.append("X-Mesh-Request-Id", requestId());
  h.append("X-Mesh-Content-Type", "application/json");

  const started = performance.now();
  try {
    const resp = await nc.request(
      `mesh.agent.${name}`,
      JSON.stringify(payload ?? {}),
      { timeout: timeoutMs, headers: h },
    );
    const elapsedMs = performance.now() - started;
    const status = resp.headers?.get("X-Mesh-Status") ?? "";
    if (status === "error") {
      const err = resp.json<Record<string, unknown>>();
      return {
        ok: false,
        elapsedMs,
        error: {
          code: String(err.code ?? "unknown"),
          message: String(err.message ?? "Unknown error"),
          agent: String(err.agent ?? name),
          details: (err.details as Record<string, unknown>) ?? {},
        },
      };
    }
    return { ok: true, elapsedMs, payload: resp.data.length ? resp.json() : {} };
  } catch (e) {
    const elapsedMs = performance.now() - started;
    const message =
      e instanceof Error && e.message.includes("TIMEOUT")
        ? `No reply within ${(timeoutMs / 1000).toFixed(0)}s (agent down or overloaded)`
        : String(e);
    return {
      ok: false,
      elapsedMs,
      error: { code: "transport", message, agent: name },
    };
  }
}
