import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { connectMesh, type MeshClient } from "./mesh";

export interface MeshState {
  mesh: MeshClient | null;
  status: "connecting" | "connected" | "error";
  error?: string;
}

const MeshContext = createContext<MeshState>({ mesh: null, status: "connecting" });

export function useMesh(): MeshState {
  return useContext(MeshContext);
}

/** Connects on mount and exposes the client; `client` injects a fake (tests). */
export function MeshProvider({ children, client }: { children: ReactNode; client?: MeshClient }) {
  const [state, setState] = useState<MeshState>(() =>
    client ? { mesh: client, status: "connected" } : { mesh: null, status: "connecting" },
  );

  useEffect(() => {
    if (client) return;
    let cancelled = false;
    let mesh: MeshClient | undefined;
    void connectMesh()
      .then((m) => {
        mesh = m;
        if (cancelled) void m.close();
        else setState({ mesh: m, status: "connected" });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({ mesh: null, status: "error", error: err instanceof Error ? err.message : String(err) });
        }
      });
    return () => {
      cancelled = true;
      void mesh?.close();
    };
  }, [client]);

  return <MeshContext.Provider value={state}>{children}</MeshContext.Provider>;
}
