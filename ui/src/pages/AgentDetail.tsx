import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import CapabilityBadges from "../components/CapabilityBadges";
import { useContract } from "../hooks";
import { prettyJson } from "../lib/format";

function SchemaBlock({ title, schema }: { title: string; schema?: Record<string, unknown> }) {
  if (!schema) return null;
  return (
    <section>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <pre className="overflow-x-auto rounded border border-slate-200 bg-white p-3 font-mono text-xs leading-relaxed">
        {prettyJson(schema)}
      </pre>
    </section>
  );
}

export default function AgentDetail() {
  const { name = "" } = useParams();
  const { contract, error } = useContract(name);
  const [view, setView] = useState<"human" | "json">("human");

  if (error) {
    return (
      <div>
        <p className="text-red-700">
          Agent <span className="font-mono">{name}</span> not found: {error}
        </p>
        <Link to="/" className="text-sm text-sky-700 underline">
          Back to registry
        </Link>
      </div>
    );
  }
  if (!contract) {
    return <p className="text-slate-500">Loading contract…</p>;
  }

  const toggleClass = (active: boolean) =>
    `rounded px-2.5 py-1 text-xs font-medium ${
      active ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-200"
    }`;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="font-mono text-xl font-semibold">{contract.name}</h2>
        <CapabilityBadges invocable={contract.invocable} streaming={contract.streaming} />
        <div className="ml-auto flex gap-1" role="group" aria-label="contract view">
          <button type="button" className={toggleClass(view === "human")} onClick={() => setView("human")}>
            Human
          </button>
          <button type="button" className={toggleClass(view === "json")} onClick={() => setView("json")}>
            JSON
          </button>
        </div>
      </div>

      {view === "json" ? (
        <pre className="overflow-x-auto rounded border border-slate-200 bg-white p-3 font-mono text-xs leading-relaxed">
          {prettyJson(contract)}
        </pre>
      ) : (
        <div className="space-y-4">
          <p className="text-slate-700">{contract.description}</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
            <dt className="text-slate-500">Subject</dt>
            <dd className="font-mono">{contract.subject}</dd>
            <dt className="text-slate-500">Version</dt>
            <dd className="font-mono">{contract.version}</dd>
            {contract.registeredAt && (
              <>
                <dt className="text-slate-500">Registered</dt>
                <dd className="font-mono">{contract.registeredAt}</dd>
              </>
            )}
            {contract.tags.length > 0 && (
              <>
                <dt className="text-slate-500">Tags</dt>
                <dd className="flex gap-1">
                  {contract.tags.map((t) => (
                    <span key={t} className="rounded bg-slate-200 px-1.5 py-0.5 text-xs">
                      {t}
                    </span>
                  ))}
                </dd>
              </>
            )}
          </dl>
          <SchemaBlock title="Input schema" schema={contract.inputSchema} />
          <SchemaBlock title="Output schema" schema={contract.outputSchema} />
          <SchemaBlock title="Chunk schema" schema={contract.chunkSchema} />
        </div>
      )}
    </div>
  );
}
