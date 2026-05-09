// WebSocket client + typed Svelte stores for the wildfire scenario UI.
//
// Per D-25 / D-38 the browser does NOT talk NATS directly; the dashboard
// FastAPI backend (`demos/wildfire/dashboard/server.py`) holds the mesh
// client and exposes a single `/ws` WebSocket for both reads (KV / pubsub
// fan-out) and writes (click events).
//
// Server -> browser envelopes (see `server.py` header):
//
//   { type: "cell_update", coords: {x, y}, temperature, x_idx, y_idx }
//   { type: "cell_delete", x_idx, y_idx }
//   { type: "fleet_update", instance_id, zone, fleet_type, coords, state,
//                           current_assignment, last_updated }
//   { type: "detection",   detection_id, coords, severity, state }
//   { type: "action_status", subject, payload }
//   { type: "snapshot_complete" }
//   { type: "error", reason, details }   // sent in response to bad clicks
//
// Browser -> server (only one shape today, per D-53):
//
//   { type: "click", coords: {x, y}, temperature: number | null }
//
// `temperature: null` is the "off" transition (D-50): server deletes the
// KV cell instead of writing one.

import { writable, type Writable } from "svelte/store";

// ---------------------------------------------------------------------------
// Types matching the WebSocket protocol
// ---------------------------------------------------------------------------

export type Coords = { x: number; y: number };

export type Cell = {
  x: number;
  y: number;
  temperature: number;
  x_idx: number;
  y_idx: number;
};

export type FleetMember = {
  instance_id: string;
  zone: string;
  fleet_type: string;
  coords: Coords | null;
  state: string;
  last_updated: number;
  current_assignment: string | null;
};

export type Detection = {
  detection_id: string;
  coords: Coords;
  severity: number;
  state: string;
};

export type ActionStatus = {
  subject: string;
  payload: Record<string, unknown>;
};

export type ConnectionState =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected";

// ---------------------------------------------------------------------------
// Stores
// ---------------------------------------------------------------------------
//
// Cells/fleet/detections are held in `Map`s keyed by their stable id. We
// replace the map reference on every write so Svelte's `$store` autosub
// fires; mutating the same Map in place would not.
//
// `actionStatusStore` is a bounded ring buffer (last 50) so a long-running
// demo doesn't grow unbounded.

const ACTION_STATUS_BUFFER = 50;

export const cellsStore: Writable<Map<string, Cell>> = writable(
  new Map<string, Cell>(),
);
export const fleetStore: Writable<Map<string, FleetMember>> = writable(
  new Map<string, FleetMember>(),
);
export const detectionsStore: Writable<Map<string, Detection>> = writable(
  new Map<string, Detection>(),
);
export const actionStatusStore: Writable<ActionStatus[]> = writable([]);
export const connectionStore: Writable<ConnectionState> =
  writable("disconnected");

function cellKey(xIdx: number, yIdx: number): string {
  return `${xIdx}:${yIdx}`;
}

// ---------------------------------------------------------------------------
// Outbound: shared mutable WS reference so `sendClick` can reach it.
// ---------------------------------------------------------------------------

let activeSocket: WebSocket | null = null;

/**
 * Send a `{type: "click", coords, temperature}` frame over the active
 * WebSocket. No-op (with a warning) if the socket is not OPEN; reconnect
 * logic in `openMeshWebSocket` drives recovery without callers needing to
 * retry. `temperature: null` triggers a server-side cell delete (D-50).
 */
export function sendClick(coords: Coords, temperature: number | null): void {
  if (!activeSocket || activeSocket.readyState !== WebSocket.OPEN) {
    console.warn("[mesh] sendClick: socket not open; click dropped", coords);
    return;
  }
  activeSocket.send(
    JSON.stringify({ type: "click", coords, temperature }),
  );
}

// ---------------------------------------------------------------------------
// Inbound: per-message dispatch
// ---------------------------------------------------------------------------

function applyCellUpdate(msg: {
  coords: Coords;
  temperature: number;
  x_idx: number;
  y_idx: number;
}): void {
  cellsStore.update((m) => {
    const next = new Map(m);
    const k = cellKey(msg.x_idx, msg.y_idx);
    next.set(k, {
      x: msg.coords.x,
      y: msg.coords.y,
      temperature: msg.temperature,
      x_idx: msg.x_idx,
      y_idx: msg.y_idx,
    });
    return next;
  });
}

function applyCellDelete(msg: { x_idx: number; y_idx: number }): void {
  cellsStore.update((m) => {
    const k = cellKey(msg.x_idx, msg.y_idx);
    if (!m.has(k)) return m;
    const next = new Map(m);
    next.delete(k);
    return next;
  });
}

function applyFleetUpdate(msg: FleetMember): void {
  fleetStore.update((m) => {
    const next = new Map(m);
    next.set(msg.instance_id, msg);
    return next;
  });
}

function applyDetection(msg: Detection): void {
  detectionsStore.update((m) => {
    const next = new Map(m);
    next.set(msg.detection_id, msg);
    return next;
  });
}

function applyActionStatus(msg: ActionStatus): void {
  actionStatusStore.update((arr) => {
    const next = [...arr, msg];
    if (next.length > ACTION_STATUS_BUFFER) {
      next.splice(0, next.length - ACTION_STATUS_BUFFER);
    }
    return next;
  });
}

function dispatch(raw: string): void {
  let frame: unknown;
  try {
    frame = JSON.parse(raw);
  } catch (e) {
    console.warn("[mesh] dropping malformed JSON frame", e, raw);
    return;
  }
  if (!frame || typeof frame !== "object") return;
  const msg = frame as { type?: unknown };
  switch (msg.type) {
    case "cell_update":
      applyCellUpdate(frame as Parameters<typeof applyCellUpdate>[0]);
      return;
    case "cell_delete":
      applyCellDelete(frame as Parameters<typeof applyCellDelete>[0]);
      return;
    case "fleet_update":
      applyFleetUpdate(frame as FleetMember);
      return;
    case "detection":
      applyDetection(frame as Detection);
      return;
    case "action_status":
      applyActionStatus(frame as ActionStatus);
      return;
    case "snapshot_complete":
      // Backend signals end of replay; nothing to do today, but reserved.
      return;
    case "error":
      console.warn("[mesh] server reported error frame", frame);
      return;
    default:
      console.warn("[mesh] unknown frame type", msg.type);
      return;
  }
}

// ---------------------------------------------------------------------------
// Connection lifecycle: open + reconnect with exponential backoff
// ---------------------------------------------------------------------------

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;

/**
 * Open a WebSocket against the dashboard backend's `/ws` endpoint and
 * keep it open across transient network errors. Returns a teardown
 * function that closes the socket and cancels any pending reconnect.
 *
 * The URL is derived from `location.origin` so the same code works
 * against `http://localhost:8081` (dev) and any future hosted origin
 * without a config indirection.
 */
export function openMeshWebSocket(): () => void {
  let attempt = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let closedByCaller = false;

  const url = `${location.origin.replace(/^http/, "ws")}/ws`;

  const connect = (): void => {
    if (closedByCaller) return;
    connectionStore.set(attempt === 0 ? "connecting" : "reconnecting");

    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      console.warn("[mesh] WebSocket constructor threw", e);
      scheduleReconnect();
      return;
    }
    activeSocket = ws;

    ws.addEventListener("open", () => {
      attempt = 0;
      connectionStore.set("connected");
    });

    ws.addEventListener("message", (ev: MessageEvent<string>) => {
      dispatch(ev.data);
    });

    ws.addEventListener("error", (ev) => {
      console.warn("[mesh] WebSocket error", ev);
    });

    ws.addEventListener("close", () => {
      if (activeSocket === ws) activeSocket = null;
      if (closedByCaller) {
        connectionStore.set("disconnected");
        return;
      }
      scheduleReconnect();
    });
  };

  const scheduleReconnect = (): void => {
    connectionStore.set("reconnecting");
    const delay = Math.min(
      RECONNECT_MAX_MS,
      RECONNECT_BASE_MS * Math.pow(2, attempt),
    );
    attempt += 1;
    reconnectTimer = setTimeout(connect, delay);
  };

  connect();

  return (): void => {
    closedByCaller = true;
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (activeSocket) {
      try {
        activeSocket.close();
      } catch {
        // socket already in CLOSING / CLOSED; nothing to do.
      }
      activeSocket = null;
    }
    connectionStore.set("disconnected");
  };
}
