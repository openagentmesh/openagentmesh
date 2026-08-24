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

export type Briefing = {
  incident_id: string;
  severity: "low" | "med" | "high" | "critical";
  summary: string;
  persons_estimated: number;
  structures_at_risk: number;
  recommended_actions: string[];
  sources: string[];
  confidence: number;
  issued_at: number;
  issuing_instance_id: string;
};

export type Narrative = {
  period_start: number;
  period_end: number;
  text: string;
  incident_ids_referenced: string[];
};

export type SwarmStats = {
  timestamp: number;
  uavs_active: number;
  uavs_total: number;
  drones_active: number;
  drones_total: number;
  helis_active: number;
  helis_total: number;
  ffunits_active: number;
  ffunits_total: number;
  medevacs_active: number;
  medevacs_total: number;
  incidents_open: number;
  incidents_resolved: number;
  fires_detected_total: number;
  persons_recovered_total: number;
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
// Latest briefing per incident (map) + most recent overall for the pane.
export const briefingsStore: Writable<Map<string, Briefing>> = writable(
  new Map<string, Briefing>(),
);
export const latestBriefingStore: Writable<Briefing | null> = writable(null);
export const narrativeStore: Writable<Narrative | null> = writable(null);
export const statsStore: Writable<SwarmStats | null> = writable(null);

// Human-readable mission log derived from raw frames. Bounded ring buffer;
// newest first. `tone` picks the accent in the feed pane.
export type MissionEvent = {
  t: number; // Date.now()
  text: string;
  tone: "neutral" | "ember" | "amber" | "alarm" | "ok";
};

const EVENT_BUFFER = 80;
export const eventsStore: Writable<MissionEvent[]> = writable([]);

function logEvent(text: string, tone: MissionEvent["tone"] = "neutral"): void {
  eventsStore.update((arr) => {
    const next: MissionEvent[] = [{ t: Date.now(), text, tone }, ...arr];
    if (next.length > EVENT_BUFFER) next.length = EVENT_BUFFER;
    return next;
  });
}

// Track detection + action states so the log only records transitions.
const seenDetectionStates = new Map<string, string>();
const seenActionStates = new Map<string, string>();

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

/**
 * Publish a chaos kill at the targeted instance (Phase 4). The server
 * forwards it as a ChaosKill on `mesh.chaos.kill.{instance_id}`; the
 * process dies hard and its liveness dot goes red in the admin UI.
 */
export function sendChaosKill(instanceId: string): void {
  if (!activeSocket || activeSocket.readyState !== WebSocket.OPEN) {
    console.warn("[mesh] sendChaosKill: socket not open; kill dropped");
    return;
  }
  activeSocket.send(
    JSON.stringify({ type: "chaos_kill", instance_id: instanceId }),
  );
  logEvent(`chaos kill sent to ${instanceId.slice(0, 8)}`, "alarm");
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
  // Mission log: only state transitions, not every KV rewrite.
  const prev = seenDetectionStates.get(msg.detection_id);
  const cur = String(msg.state);
  if (prev !== cur) {
    seenDetectionStates.set(msg.detection_id, cur);
    const id = msg.detection_id.slice(0, 8);
    const at = `(${msg.coords.x.toFixed(1)}, ${msg.coords.y.toFixed(1)})`;
    if (cur === "pending") {
      logEvent(`uav thermal detection ${id} ${at} sev ${msg.severity.toFixed(2)}`, "ember");
    } else if (cur.startsWith("assigned:")) {
      logEvent(`drone ${cur.slice(9, 17)} claimed detection ${id}`, "neutral");
    } else if (cur === "surveyed") {
      logEvent(`survey complete on ${id} ${at}`, "amber");
    }
  }
}

function applyActionStatus(msg: ActionStatus): void {
  actionStatusStore.update((arr) => {
    const next = [...arr, msg];
    if (next.length > ACTION_STATUS_BUFFER) {
      next.splice(0, next.length - ACTION_STATUS_BUFFER);
    }
    return next;
  });
  // Mission log: action fleet state transitions (heli dropping, medevac
  // extracting, ...). Subject shape: mesh.action.{type}.{instance}.status.
  const p = msg.payload as { instance_id?: string; state?: string } | null;
  if (!p?.instance_id || !p?.state) return;
  const prev = seenActionStates.get(p.instance_id);
  if (prev === p.state) return;
  seenActionStates.set(p.instance_id, p.state);
  const type = msg.subject.split(".")[2] ?? "unit";
  const id = p.instance_id.slice(0, 8);
  if (p.state === "acting") {
    const verb = type === "heli" ? "dropping water" : type === "medevac" ? "extracting" : "suppressing";
    logEvent(`${type} ${id} ${verb}`, "ok");
  } else if (p.state !== "free") {
    logEvent(`${type} ${id} ${p.state.replace("_", " ")}`, "neutral");
  }
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
    case "briefing": {
      const b = (frame as { payload: Briefing }).payload;
      if (!b || typeof b !== "object") return;
      briefingsStore.update((m) => {
        const next = new Map(m);
        next.set(b.incident_id, b);
        return next;
      });
      latestBriefingStore.set(b);
      logEvent(`briefer issued ${b.incident_id} severity ${b.severity}`, "amber");
      return;
    }
    case "narrative": {
      const n = (frame as { payload: Narrative }).payload;
      if (n && typeof n === "object") narrativeStore.set(n);
      return;
    }
    case "stats": {
      const s = (frame as { payload: SwarmStats }).payload;
      if (s && typeof s === "object") statsStore.set(s);
      return;
    }
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
