import { NavLink, Route, Routes } from "react-router-dom";
import { useMesh } from "./MeshProvider";
import AgentDetail from "./pages/AgentDetail";
import Events from "./pages/Events";
import Registry from "./pages/Registry";

function ConnectionBadge() {
  const { status, error } = useMesh();
  const styles: Record<string, string> = {
    connecting: "bg-amber-100 text-amber-800",
    connected: "bg-emerald-100 text-emerald-800",
    error: "bg-red-100 text-red-800",
  };
  return (
    <span
      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status]}`}
      title={error ?? undefined}
    >
      {status}
    </span>
  );
}

export default function App() {
  const navClass = ({ isActive }: { isActive: boolean }) =>
    `rounded px-3 py-1.5 text-sm font-medium ${
      isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-200"
    }`;
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
          <span className="text-lg font-semibold tracking-tight">OAM Admin</span>
          <nav className="flex gap-1">
            <NavLink to="/" end className={navClass}>
              Registry
            </NavLink>
            <NavLink to="/events" className={navClass}>
              Events
            </NavLink>
          </nav>
          <div className="ml-auto">
            <ConnectionBadge />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Registry />} />
          <Route path="/agents/:name" element={<AgentDetail />} />
          <Route path="/events" element={<Events />} />
        </Routes>
      </main>
    </div>
  );
}
