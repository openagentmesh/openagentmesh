import { useState } from "react";
import { CatalogEntry } from "../lib/catalog";
import { FleetMember, isLive } from "../lib/fleet";
import { groupCatalog } from "../lib/grouping";

type Props = {
  catalog: CatalogEntry[];
  fleet: Record<string, FleetMember>;
  selected: string | null;
  onSelect: (name: string) => void;
};

type Liveness = {
  live: number;
  total: number;
  // Agents outside wildfire.fleet.* (fire-sim, LLM peers) have no heartbeat
  // records; their liveness is unknown, not dead.
  known: boolean;
};

// Records staler than this drop out of the totals entirely: leftover
// heartbeats from a previous run would otherwise inflate counts forever.
// A freshly killed agent stays visible (red) for the full window, which is
// what the chaos demo needs; week-old restart garbage hides.
const HIDE_AFTER_MS = 120_000;

function instancesFor(name: string, fleet: Record<string, FleetMember>): Liveness {
  const [zone, type] = name.split(".", 2);
  if (!type) return { live: 0, total: 0, known: false };
  let total = 0;
  let live = 0;
  const now = Date.now();
  for (const k of Object.keys(fleet)) {
    const segs = k.split(".");
    if (segs.length < 5) continue;
    if (segs[2] === zone && segs[3] === type) {
      const m = fleet[k];
      if (now - m.last_updated * 1000 > HIDE_AFTER_MS) continue;
      total++;
      if (isLive(m, now)) live++;
    }
  }
  return { live, total, known: total > 0 };
}

function LivenessDot({ l }: { l: Liveness }) {
  if (!l.known) return <span className="dot bg-ink-600" title="no heartbeat surface" />;
  if (l.live > 0) return <span className="dot bg-live" />;
  return <span className="dot animate-pulse-dot bg-dead" />;
}

export function RegistryTable({ catalog, fleet, selected, onSelect }: Props) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const groups = groupCatalog(catalog);

  if (catalog.length === 0) {
    return (
      <div className="flex h-40 flex-col items-center justify-center gap-1 text-center">
        <p className="text-sm text-ink-300">No agents registered</p>
        <p className="text-[11px] text-ink-500">
          Waiting for the mesh catalog. Is the fleet running?
        </p>
      </div>
    );
  }

  return (
    <table className="w-full">
      <thead>
        <tr className="border-b border-ink-700 text-left">
          <th className="microlabel px-3 py-2">Agent</th>
          <th className="microlabel px-3 py-2">Capabilities</th>
          <th className="microlabel px-3 py-2 text-right">Instances</th>
        </tr>
      </thead>
      {groups.map((g) => {
        const isCollapsed = collapsed[g.key] ?? false;
        const rollup = g.entries.reduce(
          (acc, e) => {
            const l = instancesFor(e.name, fleet);
            return { live: acc.live + l.live, total: acc.total + l.total };
          },
          { live: 0, total: 0 },
        );
        return (
          <tbody key={g.key}>
            <tr
              className="cursor-pointer select-none border-b border-ink-800 bg-ink-850/60 transition-colors hover:bg-ink-800"
              onClick={() => setCollapsed((c) => ({ ...c, [g.key]: !isCollapsed }))}
            >
              <td className="px-3 py-1.5" colSpan={2}>
                <span
                  className={`mr-1.5 inline-block text-[9px] text-ink-400 transition-transform ${isCollapsed ? "" : "rotate-90"}`}
                >
                  ▸
                </span>
                <span className="microlabel">{g.label}</span>
                <span className="ml-2 font-mono text-[10px] text-ink-500">
                  {g.entries.length}
                </span>
              </td>
              <td className="px-3 py-1.5 text-right font-mono text-[10px] tabular-nums text-ink-500">
                {rollup.total > 0 ? `${rollup.live}/${rollup.total} live` : ""}
              </td>
            </tr>
            {!isCollapsed &&
              g.entries.map((c) => {
                const l = instancesFor(c.name, fleet);
                const isSel = selected === c.name;
                return (
                  <tr
                    key={c.name}
                    onClick={() => onSelect(c.name)}
                    className={`cursor-pointer border-b border-ink-800 transition-colors last:border-0 ${
                      isSel ? "bg-ember-600/10" : "hover:bg-ink-850"
                    }`}
                  >
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-mono text-xs ${isSel ? "text-ember-300" : "text-ink-100"}`}
                        >
                          {c.name}
                        </span>
                      </div>
                      <p className="mt-0.5 line-clamp-1 max-w-[36ch] text-[11px] text-ink-500">
                        {c.description}
                      </p>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1">
                        {c.invocable && (
                          <span className="rounded border border-ink-600 px-1 py-px font-mono text-[9px] uppercase tracking-wider text-ink-300">
                            call
                          </span>
                        )}
                        {c.streaming && (
                          <span className="rounded border border-ink-600 px-1 py-px font-mono text-[9px] uppercase tracking-wider text-ink-300">
                            stream
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className="inline-flex items-center gap-1.5 font-mono text-xs tabular-nums text-ink-200">
                        <LivenessDot l={l} />
                        {l.known ? `${l.live}/${l.total}` : "—"}
                      </span>
                    </td>
                  </tr>
                );
              })}
          </tbody>
        );
      })}
    </table>
  );
}
