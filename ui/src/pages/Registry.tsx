import { useNavigate } from "react-router-dom";
import CapabilityBadges from "../components/CapabilityBadges";
import { useCatalog } from "../hooks";
import { firstSentence } from "../lib/format";

export default function Registry() {
  const entries = useCatalog();
  const navigate = useNavigate();

  if (entries === null) {
    return <p className="text-slate-500">Loading catalog…</p>;
  }
  if (entries.length === 0) {
    return <p className="text-slate-500">No agents registered on this mesh yet.</p>;
  }
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-slate-300 text-left text-xs uppercase tracking-wide text-slate-500">
          <th className="px-3 py-2">Agent</th>
          <th className="px-3 py-2">Capabilities</th>
          <th className="px-3 py-2">Description</th>
          <th className="px-3 py-2">Version</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr
            key={e.name}
            onClick={() => void navigate(`/agents/${encodeURIComponent(e.name)}`)}
            className="cursor-pointer border-b border-slate-200 bg-white hover:bg-slate-100"
          >
            <td className="px-3 py-2 font-mono font-medium">{e.name}</td>
            <td className="px-3 py-2">
              <CapabilityBadges invocable={e.invocable} streaming={e.streaming} />
            </td>
            <td className="px-3 py-2 text-slate-600">{firstSentence(e.description)}</td>
            <td className="px-3 py-2 font-mono text-xs text-slate-500">{e.version}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
