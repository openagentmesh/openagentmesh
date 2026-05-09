import { CatalogEntry } from "../lib/catalog";
import { FleetMember, isLive } from "../lib/fleet";

type Props = {
  catalog: CatalogEntry[];
  fleet: Record<string, FleetMember>;
};

function instancesFor(
  name: string,
  fleet: Record<string, FleetMember>,
): { live: number; total: number } {
  // Channel-prefixed agent names look like "<zone>.<type>" (e.g. "high-alt.uav",
  // "low-alt.drone"). Fleet keys live under wildfire.fleet.<zone>.<type>.<instance_id>.
  const [zone, type] = name.split(".", 2);
  let total = 0;
  let live = 0;
  const now = Date.now();
  for (const k of Object.keys(fleet)) {
    const segs = k.split(".");
    if (segs.length < 5) continue;
    if (segs[2] === zone && segs[3] === type) {
      total++;
      if (isLive(fleet[k], now)) live++;
    }
  }
  return { live, total };
}

export function RegistryTable({ catalog, fleet }: Props) {
  return (
    <table className="min-w-full divide-y divide-gray-200">
      <thead className="bg-gray-100">
        <tr>
          <th className="px-4 py-2 text-left text-xs font-semibold uppercase">Name</th>
          <th className="px-4 py-2 text-left text-xs font-semibold uppercase">Capabilities</th>
          <th className="px-4 py-2 text-left text-xs font-semibold uppercase">Instances</th>
          <th className="px-4 py-2 text-left text-xs font-semibold uppercase">Description</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-200">
        {catalog.map((c) => {
          const { live, total } = instancesFor(c.name, fleet);
          // Status dot: green if any live instance, yellow if registered but
          // every instance is stale, gray if no fleet record at all (e.g. an
          // agent that does not heartbeat into wildfire.fleet.>).
          const dot = live > 0 ? "🟢" : total > 0 ? "🟡" : "⚫";
          return (
            <tr key={c.name}>
              <td className="px-4 py-2 font-mono text-sm">{c.name}</td>
              <td className="px-4 py-2 text-xs">
                {c.invocable ? "📞 invocable " : ""}
                {c.streaming ? "📡 streaming" : ""}
              </td>
              <td className="px-4 py-2 text-sm">
                {dot} {live}/{total}
              </td>
              <td className="px-4 py-2 text-xs text-gray-700">{c.description}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
