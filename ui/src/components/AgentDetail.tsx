import { useEffect, useRef, useState } from "react";
import {
  AgentRegistryDoc,
  JsonSchema,
  inputSchemaOf,
  outputSchemaOf,
  resolveRef,
} from "../lib/registry";
import { MeshCallResult, callAgent } from "../lib/invoke";
import { SchemaForm } from "./SchemaForm";

// Per-agent detail: contract header, input/output JSON Schemas, and the
// schema-driven invocation sandbox (ADR-0056 wave 3). LLM-backed agents
// take seconds to reply, so the in-flight state is a first-class surface:
// a labeled "thinking" row with a live elapsed timer, never a frozen pane.
type Props = {
  doc: AgentRegistryDoc;
  onClose: () => void;
};

export function AgentDetail({ doc, onClose }: Props) {
  const [inflight, setInflight] = useState(false);
  const [result, setResult] = useState<MeshCallResult | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Reset sandbox state when switching agents.
  useEffect(() => {
    setInflight(false);
    setResult(null);
    setElapsed(0);
  }, [doc.name]);

  useEffect(() => {
    if (inflight) {
      const started = performance.now();
      timerRef.current = setInterval(
        () => setElapsed(performance.now() - started),
        100,
      );
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [inflight]);

  const inputSchema = inputSchemaOf(doc);
  const outputSchema = outputSchemaOf(doc);
  const invocable = doc.capabilities?.invocable ?? false;

  async function invoke(payload: unknown) {
    setInflight(true);
    setResult(null);
    const res = await callAgent(doc.name, payload);
    setResult(res);
    setInflight(false);
  }

  return (
    <section className="panel flex h-full min-h-0 flex-col">
      <header className="flex items-start justify-between border-b border-ink-700 px-3 py-2.5">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-mono text-sm font-semibold text-ink-50">{doc.name}</h2>
            <span className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-ink-300">
              v{doc.version}
            </span>
            {doc.capabilities?.invocable && <CapBadge label="call" />}
            {doc.capabilities?.streaming && <CapBadge label="stream" />}
          </div>
          {doc["x-agentmesh"]?.subject && (
            <p className="mt-0.5 font-mono text-[11px] text-ink-400">
              {doc["x-agentmesh"].subject}
            </p>
          )}
        </div>
        <button
          onClick={onClose}
          aria-label="close-detail"
          className="rounded px-1.5 py-0.5 text-ink-400 transition-colors hover:bg-ink-800 hover:text-ink-100"
        >
          ×
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
        <p className="text-xs leading-relaxed text-ink-200">{doc.description}</p>

        {invocable && inputSchema && (
          <div>
            <h3 className="microlabel mb-2">Invoke — {schemaTitle(inputSchema) ?? "input"}</h3>
            <SchemaForm
              schema={inputSchema}
              disabled={inflight}
              onSubmit={invoke}
              submitLabel={inflight ? "Calling…" : `Call ${doc.name}`}
            />
          </div>
        )}

        {inflight && (
          <div className="flex items-center gap-2 rounded border border-ink-700 bg-ink-850 px-3 py-2.5">
            <span className="dot animate-pulse-dot bg-ember-400" />
            <span className="text-xs text-ink-200">
              <span className="font-mono text-ember-300">{doc.name}</span> is thinking
            </span>
            <span className="ml-auto font-mono text-[11px] tabular-nums text-ink-400">
              {(elapsed / 1000).toFixed(1)}s
            </span>
          </div>
        )}

        {result && !inflight && (
          <ResultPane result={result} outputSchema={outputSchema} />
        )}

        {inputSchema && (
          <SchemaBlock title="Input schema" schema={inputSchema} />
        )}
        {outputSchema && (
          <SchemaBlock title="Output schema" schema={outputSchema} />
        )}
        {!invocable && !inputSchema && (
          <p className="text-[11px] text-ink-400">
            Background agent: no invocation surface. Watch its output on the event feed.
          </p>
        )}
      </div>
    </section>
  );
}

function schemaTitle(s: JsonSchema): string | undefined {
  return typeof s.title === "string" ? s.title : undefined;
}

function CapBadge({ label }: { label: string }) {
  return (
    <span className="rounded border border-ink-600 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-ink-300">
      {label}
    </span>
  );
}

function ResultPane({
  result,
  outputSchema,
}: {
  result: MeshCallResult;
  outputSchema?: JsonSchema;
}) {
  if (!result.ok) {
    return (
      <div className="rounded border border-dead/40 bg-dead/10 px-3 py-2.5">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-wider text-dead">
            {result.error.code}
          </span>
          <span className="font-mono text-[11px] tabular-nums text-ink-400">
            {(result.elapsedMs / 1000).toFixed(2)}s
          </span>
        </div>
        <p className="mt-1 text-xs text-ink-100">{result.error.message}</p>
      </div>
    );
  }

  const payload = result.payload;
  const fields =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? Object.entries(payload as Record<string, unknown>)
      : null;
  const title = outputSchema?.title ?? "Result";

  return (
    <div className="animate-feed-in rounded border border-live/30 bg-live/5 px-3 py-2.5">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wider text-live">
          {title}
        </span>
        <span className="font-mono text-[11px] tabular-nums text-ink-400">
          {(result.elapsedMs / 1000).toFixed(2)}s
        </span>
      </div>
      {fields ? (
        <dl className="mt-2 space-y-1">
          {fields.map(([k, v]) => (
            <div key={k} className="flex gap-2 text-xs">
              <dt className="w-36 shrink-0 font-mono text-ink-400">{k}</dt>
              <dd className="min-w-0 break-words font-mono text-ink-100">
                {typeof v === "object" ? JSON.stringify(v) : String(v)}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-xs text-ink-100">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

function SchemaBlock({ title, schema }: { title: string; schema: JsonSchema }) {
  const [open, setOpen] = useState(false);
  const props = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="microlabel flex items-center gap-1 transition-colors hover:text-ink-200"
      >
        <span className={`inline-block transition-transform ${open ? "rotate-90" : ""}`}>▸</span>
        {title}
        {schema.title && <span className="normal-case tracking-normal text-ink-500">· {schema.title}</span>}
      </button>
      {open && (
        <table className="mt-1.5 w-full">
          <tbody>
            {Object.entries(props).map(([name, raw]) => {
              const s = resolveRef(schema, raw) ?? raw;
              return (
                <tr key={name} className="border-b border-ink-800 last:border-0">
                  <td className="py-1 pr-2 align-top font-mono text-[11px] text-ink-200">
                    {name}
                    {required.has(name) && <span className="text-ember-500">*</span>}
                  </td>
                  <td className="py-1 pr-2 align-top font-mono text-[11px] text-ink-400">
                    {typeLabel(s)}
                  </td>
                  <td className="py-1 align-top text-[11px] text-ink-400">
                    {s.description ?? ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function typeLabel(s: JsonSchema): string {
  if (Array.isArray(s.enum)) return s.enum.map(String).join(" | ");
  if (s.anyOf) return s.anyOf.map((v) => typeLabel(v)).join(" | ");
  if (s.type === "array") return `${s.items ? typeLabel(s.items) : "any"}[]`;
  if (s.$ref) return s.$ref.replace("#/$defs/", "");
  return s.type ?? "any";
}
