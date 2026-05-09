// Hand-rolled HTMLCanvas + 2D-context renderer for the wildfire dashboard.
//
// Decoupled from Svelte: takes a callback that returns the latest store
// snapshot. App.svelte (Task 4) wires this against the writable stores
// from `mesh.ts`. The renderer redraws on every `requestAnimationFrame`
// (browser-paced ~60 fps; cheap because the scene is a 50x50 grid + a
// handful of pointers + at most a few hundred trail points).
//
// Layer order (per `km/specs/wildfire/dashboard.md` "Behaviour notes"):
//
//   1. heat layer        (semi-transparent quads keyed by temperature)
//   2. drone trails      (last 30 s of positions per drone / medevac)
//   3. detection markers (transient flash for pending; persistent for surveyed)
//   4. fleet pointers    (UAV triangle, drone dot, heli rotor, ffunit cross,
//                          medevac square)
//
// Pointer shapes mirror the spec:
// - UAV: upward triangle
// - drone: filled small dot
// - heli: open circle with rotor bar
// - ffunit: cross
// - medevac: filled square

import {
  GRID_DIM,
  WORLD_MAX_KM,
  WORLD_MIN_KM,
  kmToPixel,
} from "./coords";
import type { Cell, Detection, FleetMember } from "./mesh";

export interface RenderState {
  cells: Map<string, Cell>;
  fleet: Map<string, FleetMember>;
  detections: Map<string, Detection>;
}

const TRAIL_WINDOW_S = 30;
const TRAIL_MIN_DELTA_KM = 0.05; // ~50 m: keeps the buffer cheap.

// Background "world frame" color drawn once per redraw before any layers.
const WORLD_BG = "#f4f1ea";

export class Renderer {
  private trails: Map<string, Array<{ x: number; y: number; t: number }>> =
    new Map();
  private rafId = 0;
  private running = false;

  constructor(
    private canvas: HTMLCanvasElement,
    private getState: () => RenderState,
  ) {}

  start(): void {
    if (this.running) return;
    this.running = true;
    const loop = (): void => {
      if (!this.running) return;
      this.draw();
      this.rafId = requestAnimationFrame(loop);
    };
    this.rafId = requestAnimationFrame(loop);
  }

  stop(): void {
    this.running = false;
    if (this.rafId !== 0) {
      cancelAnimationFrame(this.rafId);
      this.rafId = 0;
    }
  }

  private draw(): void {
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    const w = this.canvas.width;
    const h = this.canvas.height;
    if (w === 0 || h === 0) return;

    // World background.
    ctx.fillStyle = WORLD_BG;
    ctx.fillRect(0, 0, w, h);

    const state = this.getState();

    // ---- Layer 1: heat layer ----------------------------------------
    //
    // Map cell temperature in [25, 800] °C (FIRE_SIM_AMBIENT_C ..
    // FIRE_SIM_MAX_C in core/config.py) onto a yellow -> orange -> red
    // gradient with rising opacity. Cells outside that range are
    // clamped; alpha cap of 0.7 keeps fleet pointers legible on top.
    const cellPxW = w / GRID_DIM;
    const cellPxH = h / GRID_DIM;
    for (const cell of state.cells.values()) {
      const intensity = Math.min(
        1,
        Math.max(0, (cell.temperature - 25) / 775),
      );
      const green = Math.floor(200 * (1 - intensity));
      ctx.fillStyle = `rgba(255, ${green}, 0, ${0.2 + 0.5 * intensity})`;
      const xPx = cell.x_idx * cellPxW;
      const yPx = cell.y_idx * cellPxH;
      ctx.fillRect(xPx, yPx, cellPxW, cellPxH);
    }

    // ---- Layer 2: drone / medevac trails ----------------------------
    //
    // Append-and-trim: push a new point only if the fleet member moved
    // at least TRAIL_MIN_DELTA_KM since the last sample; drop points
    // older than TRAIL_WINDOW_S seconds. This keeps the trail buffer
    // bounded (T-02-07-03 mitigation).
    const now = Date.now() / 1000;
    for (const member of state.fleet.values()) {
      if (member.coords === null) continue;
      if (member.fleet_type !== "drone" && member.fleet_type !== "medevac") {
        continue;
      }
      let trail = this.trails.get(member.instance_id);
      if (!trail) {
        trail = [];
        this.trails.set(member.instance_id, trail);
      }
      const last = trail[trail.length - 1];
      if (
        !last ||
        Math.hypot(
          last.x - member.coords.x,
          last.y - member.coords.y,
        ) > TRAIL_MIN_DELTA_KM
      ) {
        trail.push({ x: member.coords.x, y: member.coords.y, t: now });
      }
      while (trail.length > 0 && trail[0].t < now - TRAIL_WINDOW_S) {
        trail.shift();
      }
      if (trail.length > 1) {
        ctx.strokeStyle = "rgba(0, 100, 255, 0.4)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let i = 0; i < trail.length; i++) {
          const p = trail[i];
          const { px, py } = kmToPixel(p.x, p.y, w, h);
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.stroke();
      }
    }

    // ---- Layer 3: detection markers ---------------------------------
    //
    // Pending detections render small + warm-orange (transient feel);
    // surveyed detections render larger + amber (persistent confirmed
    // marker). Severity could modulate radius later; for v1 the
    // surveyed/pending split is the only signal.
    for (const det of state.detections.values()) {
      const { px, py } = kmToPixel(det.coords.x, det.coords.y, w, h);
      const surveyed = det.state === "surveyed";
      ctx.fillStyle = surveyed
        ? "rgba(255, 200, 0, 0.9)"
        : "rgba(255, 80, 0, 0.9)";
      ctx.beginPath();
      ctx.arc(px, py, surveyed ? 6 : 4, 0, 2 * Math.PI);
      ctx.fill();
    }

    // ---- Layer 4: fleet pointers ------------------------------------
    for (const m of state.fleet.values()) {
      if (m.coords === null) continue;
      const { px, py } = kmToPixel(m.coords.x, m.coords.y, w, h);
      drawPointer(ctx, m.fleet_type, px, py);
    }

    // The world bounds (debug-friendly subtle outline). Keep at the end
    // so it sits above the heat layer; subtle alpha keeps it from
    // competing with markers.
    ctx.strokeStyle = "rgba(0, 0, 0, 0.15)";
    ctx.lineWidth = 1;
    ctx.strokeRect(0, 0, w, h);

    // Reference the WORLD constants so an unused-import lint does not
    // strip them. They're documentation here, not just type sugar.
    void WORLD_MIN_KM;
    void WORLD_MAX_KM;
  }
}

function drawPointer(
  ctx: CanvasRenderingContext2D,
  type: string,
  px: number,
  py: number,
): void {
  ctx.save();
  ctx.translate(px, py);
  ctx.fillStyle = "rgba(20, 20, 20, 0.9)";
  ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
  ctx.lineWidth = 1;
  switch (type) {
    case "uav":
      ctx.beginPath();
      ctx.moveTo(0, -8);
      ctx.lineTo(7, 6);
      ctx.lineTo(-7, 6);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      break;
    case "drone":
      ctx.beginPath();
      ctx.arc(0, 0, 3, 0, 2 * Math.PI);
      ctx.fill();
      break;
    case "heli":
      ctx.beginPath();
      ctx.arc(0, 0, 6, 0, 2 * Math.PI);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(-9, 0);
      ctx.lineTo(9, 0);
      ctx.stroke();
      break;
    case "ffunit":
      ctx.beginPath();
      ctx.moveTo(-5, -5);
      ctx.lineTo(5, 5);
      ctx.moveTo(5, -5);
      ctx.lineTo(-5, 5);
      ctx.stroke();
      break;
    case "medevac":
      ctx.fillRect(-5, -5, 10, 10);
      break;
    default:
      ctx.beginPath();
      ctx.arc(0, 0, 3, 0, 2 * Math.PI);
      ctx.fill();
  }
  ctx.restore();
}
