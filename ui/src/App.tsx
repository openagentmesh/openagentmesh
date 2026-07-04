import { useEffect, useState } from "react";
import { CatalogEntry, watchCatalog } from "./lib/catalog";
import { FleetMember, watchFleet } from "./lib/fleet";
import { AgentRegistryDoc, watchRegistry } from "./lib/registry";
import { RegistryTable } from "./components/RegistryTable";
import { EventFeed } from "./components/EventFeed";
import { AgentDetail } from "./components/AgentDetail";

export default function App() {
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [fleet, setFleet] = useState<Record<string, FleetMember>>({});
  const [registry, setRegistry] = useState<Record<string, AgentRegistryDoc>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [connected, setConnected] = useState<boolean>(false);
  // Force a re-render every second so liveness staleness updates without a KV
  // event (otherwise an agent could go stale without the row reflecting it).
  const [, setTick] = useState(0);

  useEffect(() => {
    const stops: Array<() => void> = [];
    watchCatalog((c) => {
      setConnected(true);
      setCatalog(c);
    }).then((s) => stops.push(s));
    watchFleet(setFleet).then((s) => stops.push(s));
    watchRegistry(setRegistry).then((s) => stops.push(s));
    const interval = setInterval(() => setTick((t) => t + 1), 1_000);
    return () => {
      stops.forEach((s) => s());
      clearInterval(interval);
    };
  }, []);

  const selectedDoc = selected ? registry[selected] : undefined;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b border-ink-700 bg-ink-900 px-4 py-2">
        <h1 className="text-sm font-semibold tracking-tight text-ink-50">
          OpenAgentMesh
          <span className="ml-1.5 font-normal text-ink-400">Admin</span>
        </h1>
        <span className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-ink-300">
          {catalog.length} agents
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[11px] text-ink-400">
          <span className={`dot ${connected ? "bg-live" : "animate-pulse-dot bg-stale"}`} />
          {connected ? "connected" : "connecting"}
        </span>
      </header>

      <main className="grid min-h-0 flex-1 gap-3 p-3" style={{ gridTemplateColumns: selectedDoc ? "5fr 4fr 4fr" : "1fr 1fr" }}>
        <div className="panel min-h-0 overflow-y-auto">
          <RegistryTable
            catalog={catalog}
            fleet={fleet}
            selected={selected}
            onSelect={(name) => setSelected((cur) => (cur === name ? null : name))}
          />
        </div>
        {selectedDoc && (
          <AgentDetail doc={selectedDoc} onClose={() => setSelected(null)} />
        )}
        <div className="panel min-h-0">
          <EventFeed />
        </div>
      </main>
    </div>
  );
}
