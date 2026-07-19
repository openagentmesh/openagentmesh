import { useCallback, useRef, useState } from "react";
import Form from "@rjsf/core";
import validator from "@rjsf/validator-ajv8";
import type { RJSFSchema } from "@rjsf/utils";
import { AbortError, MeshError } from "@openagentmesh/sdk";
import type { AgentContract, Json } from "@openagentmesh/sdk";
import { useMesh } from "../MeshProvider";
import { prettyJson } from "../lib/format";

interface ErrorInfo {
  code: string;
  message: string;
  agent?: string;
  requestId?: string;
}

type Phase = "idle" | "running" | "done" | "stopped" | "error";

interface RunState {
  phase: Phase;
  /** Reply from call(); undefined for streams. */
  result?: Json;
  /** Accumulated stream chunks, in arrival order. */
  chunks: Json[];
  error?: ErrorInfo;
}

const IDLE: RunState = { phase: "idle", chunks: [] };

function toErrorInfo(err: unknown): ErrorInfo {
  if (err instanceof MeshError) {
    return { code: err.code, message: err.message, agent: err.agent, requestId: err.requestId };
  }
  return { code: "error", message: err instanceof Error ? err.message : String(err) };
}

/** Per-code operator hints; only codes where the next step isn't obvious. */
const ERROR_HINTS: Record<string, string> = {
  not_available:
    "The agent is registered but its lifecycle gate is closed (or it is between instances) — safe to retry.",
  timeout: "The agent may be busy or gone mid-request — a retry is safe for idempotent handlers.",
};

function ErrorBox({ error }: { error: ErrorInfo }) {
  const hint = ERROR_HINTS[error.code];
  return (
    <div className="space-y-1 rounded border border-red-200 bg-red-50 p-3 text-sm">
      <div className="flex items-center gap-2">
        <span className="rounded bg-red-100 px-1.5 py-0.5 font-mono text-xs font-semibold text-red-800">
          {error.code}
        </span>
        <span className="text-red-900">{error.message}</span>
      </div>
      {error.requestId && (
        <p className="font-mono text-xs text-red-700">request_id: {error.requestId}</p>
      )}
      {hint && <p className="text-xs text-red-700">{hint}</p>}
    </div>
  );
}

function ChunkList({ chunks, phase }: { chunks: Json[]; phase: Phase }) {
  if (chunks.length === 0 && phase === "running") {
    return <p className="text-sm text-slate-500">Waiting for the first chunk…</p>;
  }
  if (chunks.length === 0) return null;
  return (
    <div className="space-y-1">
      {chunks.map((chunk, i) => (
        // Chunks are append-only, so the index is a stable key.
        <pre
          key={i}
          className="overflow-x-auto rounded border border-slate-200 bg-white p-2 font-mono text-xs leading-relaxed"
        >
          {prettyJson(chunk)}
        </pre>
      ))}
    </div>
  );
}

function StatusLine({ state }: { state: RunState }) {
  const { phase, chunks } = state;
  if (phase !== "done" && phase !== "stopped") return null;
  const count = `${chunks.length} chunk${chunks.length === 1 ? "" : "s"}`;
  return (
    <p className="text-xs text-slate-500">
      {phase === "stopped" ? `stopped after ${count}` : state.result === undefined ? `done · ${count}` : "done"}
    </p>
  );
}

/**
 * The invocation sandbox (ADR-0056 wave 3): an input form generated from the
 * contract's input schema, wired to the SDK's call()/stream() picked by the
 * agent's shape. Source-only agents render nothing — there is no subject to
 * request on.
 */
export default function InvokePanel({ contract }: { contract: AgentContract }) {
  const { mesh } = useMesh();
  const [state, setState] = useState<RunState>(IDLE);
  const abortRef = useRef<AbortController | null>(null);

  const streaming = contract.streaming;

  const run = useCallback(
    async (payload?: unknown) => {
      if (!mesh) return;
      setState({ phase: "running", chunks: [] });
      if (streaming) {
        const abort = new AbortController();
        abortRef.current = abort;
        try {
          for await (const chunk of mesh.stream(contract.name, payload, { signal: abort.signal })) {
            setState((s) => ({ ...s, chunks: [...s.chunks, chunk] }));
          }
          setState((s) => ({ ...s, phase: "done" }));
        } catch (err) {
          if (err instanceof AbortError) {
            setState((s) => ({ ...s, phase: "stopped" }));
          } else {
            setState((s) => ({ ...s, phase: "error", error: toErrorInfo(err) }));
          }
        } finally {
          abortRef.current = null;
        }
      } else {
        try {
          const result = await mesh.call(contract.name, payload);
          setState({ phase: "done", result, chunks: [] });
        } catch (err) {
          setState({ phase: "error", error: toErrorInfo(err), chunks: [] });
        }
      }
    },
    [mesh, contract.name, streaming],
  );

  if (!contract.invocable && !contract.streaming) return null;

  const running = state.phase === "running";
  const buttonLabel = streaming ? "Stream" : "Call";
  const submitButton = (
    <div className="flex items-center gap-2">
      <button
        type="submit"
        disabled={running}
        className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
      >
        {buttonLabel}
      </button>
      {streaming && running && (
        <button
          type="button"
          onClick={() => abortRef.current?.abort()}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
        >
          Stop
        </button>
      )}
    </div>
  );

  return (
    <section className="space-y-3 rounded border border-slate-200 bg-slate-100/60 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Invoke</h3>
      {contract.inputSchema ? (
        <Form
          schema={contract.inputSchema as RJSFSchema}
          validator={validator}
          onSubmit={({ formData }) => void run(formData)}
          showErrorList={false}
        >
          {submitButton}
        </Form>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
        >
          {submitButton}
        </form>
      )}

      {state.result !== undefined && (
        <pre className="overflow-x-auto rounded border border-slate-200 bg-white p-3 font-mono text-xs leading-relaxed">
          {prettyJson(state.result)}
        </pre>
      )}
      <ChunkList chunks={state.chunks} phase={state.phase} />
      <StatusLine state={state} />
      {state.error && <ErrorBox error={state.error} />}
    </section>
  );
}
