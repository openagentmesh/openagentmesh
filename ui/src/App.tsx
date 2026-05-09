import { useEffect, useState } from "react";
import { CatalogEntry, watchCatalog } from "./lib/catalog";
import { FleetMember, watchFleet } from "./lib/fleet";
import { RegistryTable } from "./components/RegistryTable";
import { EventFeed } from "./components/EventFeed";

export default function App() {
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [fleet, setFleet] = useState<Record<string, FleetMember>>({});
  // Force a re-render every second so liveness staleness updates without a KV
  // event (otherwise an agent could go stale without the row reflecting it).
  const [, setTick] = useState(0);

  useEffect(() => {
    let stopCatalog: (() => void) | null = null;
    let stopFleet: (() => void) | null = null;
    watchCatalog(setCatalog).then((s) => {
      stopCatalog = s;
    });
    watchFleet(setFleet).then((s) => {
      stopFleet = s;
    });
    const interval = setInterval(() => setTick((t) => t + 1), 1_000);
    return () => {
      if (stopCatalog) stopCatalog();
      if (stopFleet) stopFleet();
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">OpenAgentMesh Admin</h1>
        <p className="text-sm text-gray-600">
          Registry ({catalog.length} agents) + live event feed
        </p>
      </header>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded border border-gray-200 bg-white shadow-sm overflow-x-auto">
          <RegistryTable catalog={catalog} fleet={fleet} />
        </div>
        <div className="rounded border border-gray-200 bg-white shadow-sm h-[640px] flex flex-col">
          <EventFeed />
        </div>
      </div>
    </div>
  );
}
