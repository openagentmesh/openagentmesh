// Canvas renderer for the wildfire scenario UI (design-bar rewrite).
//
// Layer order:
//   1. terrain      (seeded offscreen skin, drawn as one image)
//   2. heat         (50x50 offscreen heat field, bilinear-upscaled so fire
//                    reads as soft organic blobs; per-cell temperatures
//                    ease toward their targets, ~250ms)
//   3. trails       (drone / medevac last-30s tracks, neutral tint)
//   4. detections   (pending pulse ring / assigned ring / surveyed diamond)
//   5. fleet        (tactical sprites, exponentially-smoothed positions;
//                    no teleporting between 1Hz heartbeats)
//   6. HQ marker + selection ring
//
// The severity ramp (ember tones) is reserved for fire, detections, and
// kill states; everything else stays in desaturated ink so the eye lands
// on the fire first.

import { GRID_DIM, kmToPixel } from "./coords";
import type { Cell, Detection, FleetMember } from "./mesh";
import { renderTerrain } from "./terrain";

export interface RenderState {
  cells: Map<string, Cell>;
  fleet: Map<string, FleetMember>;
  detections: Map<string, Detection>;
  selectedId: string | null;
}

const TRAIL_WINDOW_S = 30;
const TRAIL_MIN_DELTA_KM = 0.05;
const AMBIENT_C = 25;
const HEAT_EASE_TAU_MS = 250; // fire temperature easing
const MOVE_EASE_TAU_MS = 380; // fleet position easing
const STALE_SPRITE_MS = 6_000; // heartbeat silence -> dead styling
const GONE_SPRITE_MS = 120_000; // drop sprite entirely (old runs)

// Ember ramp: temperature -> [r, g, b, coreAlpha].
function emberColor(t: number): [number, number, number, number] {
  const stops: Array<[number, [number, number, number]]> = [
    [120, [255, 208, 138]],
    [250, [255, 183, 74]],
    [420, [255, 138, 61]],
    [600, [244, 81, 30]],
    [800, [211, 47, 47]],
  ];
  if (t <= stops[0][0]) {
    const a = Math.max(0, (t - AMBIENT_C) / (stops[0][0] - AMBIENT_C)) * 0.55;
    return [...stops[0][1], a] as [number, number, number, number];
  }
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i][0]) {
      const [t0, c0] = stops[i - 1];
      const [t1, c1] = stops[i];
      const f = (t - t0) / (t1 - t0);
      const mix = (a: number, b: number) => Math.round(a + f * (b - a));
      const alpha = 0.55 + 0.4 * Math.min(1, (t - 120) / 680);
      return [mix(c0[0], c1[0]), mix(c0[1], c1[1]), mix(c0[2], c1[2]), alpha];
    }
  }
  return [211, 47, 47, 0.95];
}

type EasedCell = { display: number; target: number; dying: boolean };
type EasedPos = { x: number; y: number; tx: number; ty: number; lastSeen: number };

// Stable per-instance jitter so units parked at the same spot (HQ) fan out
// into a countable ring instead of stacking into one glyph. The offset is
// a few pixels: invisible during travel, decisive when parked.
function instanceJitter(id: string): { jx: number; jy: number } {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) | 0;
  const angle = ((hash >>> 4) % 360) * (Math.PI / 180);
  const radius = 12 + ((hash >>> 12) % 14);
  return { jx: Math.cos(angle) * radius, jy: Math.sin(angle) * radius };
}

export class Renderer {
  private trails: Map<string, Array<{ x: number; y: number; t: number }>> = new Map();
  private heat: Map<string, EasedCell> = new Map();
  private positions: Map<string, EasedPos> = new Map();
  private rafId = 0;
  private running = false;
  private lastFrame = 0;

  private terrainCanvas: HTMLCanvasElement | null = null;
  private terrainKey = "";
  private heatField: HTMLCanvasElement;
  private heatCtx: CanvasRenderingContext2D | null;

  constructor(
    private canvas: HTMLCanvasElement,
    private getState: () => RenderState,
    private seed: number = 42,
  ) {
    this.heatField = document.createElement("canvas");
    this.heatField.width = GRID_DIM;
    this.heatField.height = GRID_DIM;
    this.heatCtx = this.heatField.getContext("2d");
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.lastFrame = performance.now();
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

  private spriteScale(): number {
    return Math.max(1.3, this.canvas.width / 1100);
  }

  /** Nearest fleet sprite within `radiusPx` of a canvas pixel, or null. */
  hitTest(px: number, py: number, radiusPx = 14): FleetMember | null {
    const state = this.getState();
    let best: FleetMember | null = null;
    let bestD = radiusPx * (window.devicePixelRatio || 1);
    for (const m of state.fleet.values()) {
      const p = this.spritePixel(m.instance_id);
      if (!p) continue;
      const d = Math.hypot(p.px - px, p.py - py);
      if (d < bestD) {
        bestD = d;
        best = m;
      }
    }
    return best;
  }

  /** Displayed pixel position of an instance (jitter included), for the
   * popover anchor and hit-testing — must match the draw path. */
  spritePixel(instanceId: string): { px: number; py: number } | null {
    const pos = this.positions.get(instanceId);
    if (!pos) return null;
    const s = this.spriteScale();
    const { jx, jy } = instanceJitter(instanceId);
    const base = kmToPixel(pos.x, pos.y, this.canvas.width, this.canvas.height);
    return { px: base.px + jx * s * 0.8, py: base.py + jy * s * 0.8 };
  }

  private draw(): void {
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    const w = this.canvas.width;
    const h = this.canvas.height;
    if (w === 0 || h === 0) return;

    const nowMs = performance.now();
    const dt = Math.min(100, nowMs - this.lastFrame);
    this.lastFrame = nowMs;
    const heatK = 1 - Math.exp(-dt / HEAT_EASE_TAU_MS);
    const moveK = 1 - Math.exp(-dt / MOVE_EASE_TAU_MS);

    const state = this.getState();

    // ---- Layer 1: terrain ------------------------------------------
    const tkey = `${w}x${h}`;
    if (!this.terrainCanvas || this.terrainKey !== tkey) {
      this.terrainCanvas = renderTerrain(w, h, this.seed);
      this.terrainKey = tkey;
    }
    ctx.drawImage(this.terrainCanvas, 0, 0);

    // ---- Layer 2: heat ----------------------------------------------
    // Sync targets from store; mark removed cells as dying (fade out).
    for (const [k, cell] of state.cells) {
      const e = this.heat.get(k);
      if (e) {
        e.target = cell.temperature;
        e.dying = false;
      } else {
        this.heat.set(k, { display: AMBIENT_C, target: cell.temperature, dying: false });
      }
    }
    for (const [k, e] of this.heat) {
      if (!state.cells.has(k)) {
        e.target = AMBIENT_C;
        e.dying = true;
      }
      e.display += (e.target - e.display) * heatK;
      if (e.dying && e.display < AMBIENT_C + 3) this.heat.delete(k);
    }

    if (this.heatCtx && this.heat.size > 0) {
      this.heatCtx.clearRect(0, 0, GRID_DIM, GRID_DIM);
      for (const [k, e] of this.heat) {
        const [xi, yi] = k.split(":").map(Number);
        const [r, g, b, a] = emberColor(e.display);
        this.heatCtx.fillStyle = `rgba(${r},${g},${b},${a})`;
        this.heatCtx.fillRect(xi, yi, 1, 1);
      }
      // Soft glow: upscale the 50x50 field with bilinear smoothing, drawn
      // twice (wide faint + tight strong) for a cheap bloom.
      ctx.save();
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.globalAlpha = 0.55;
      const bleed = Math.max(w, h) * 0.012;
      ctx.drawImage(this.heatField, -bleed, -bleed, w + 2 * bleed, h + 2 * bleed);
      ctx.globalAlpha = 0.95;
      ctx.drawImage(this.heatField, 0, 0, w, h);
      ctx.restore();
    } else if (this.heatCtx) {
      this.heatCtx.clearRect(0, 0, GRID_DIM, GRID_DIM);
    }

    // ---- Layer 3: trails --------------------------------------------
    const nowS = Date.now() / 1000;
    for (const m of state.fleet.values()) {
      if (m.coords === null) continue;
      if (m.fleet_type !== "drone" && m.fleet_type !== "medevac") continue;
      let trail = this.trails.get(m.instance_id);
      if (!trail) {
        trail = [];
        this.trails.set(m.instance_id, trail);
      }
      const last = trail[trail.length - 1];
      if (!last || Math.hypot(last.x - m.coords.x, last.y - m.coords.y) > TRAIL_MIN_DELTA_KM) {
        trail.push({ x: m.coords.x, y: m.coords.y, t: nowS });
      }
      while (trail.length > 0 && trail[0].t < nowS - TRAIL_WINDOW_S) trail.shift();
      if (trail.length > 1) {
        ctx.strokeStyle = "rgba(170, 190, 210, 0.32)";
        ctx.lineWidth = Math.max(1.2, w / 1300);
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

    // ---- Layer 4: detection markers -----------------------------------
    const pulse = (nowMs % 1600) / 1600; // 0..1 sawtooth for pending rings
    for (const det of state.detections.values()) {
      const { px, py } = kmToPixel(det.coords.x, det.coords.y, w, h);
      const s = this.spriteScale() * 0.85;
      const stateStr = String(det.state);
      if (stateStr === "pending") {
        // Expanding, fading ring: "unclaimed detection" urgency.
        const rr = (5 + pulse * 12) * s;
        ctx.strokeStyle = `rgba(255, 138, 61, ${0.85 * (1 - pulse)})`;
        ctx.lineWidth = 1.6 * s;
        ctx.beginPath();
        ctx.arc(px, py, rr, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.fillStyle = "rgba(255, 183, 74, 0.9)";
        ctx.beginPath();
        ctx.arc(px, py, 2.4 * s, 0, 2 * Math.PI);
        ctx.fill();
      } else if (stateStr.startsWith("assigned:")) {
        ctx.strokeStyle = "rgba(255, 183, 74, 0.85)";
        ctx.lineWidth = 1.4 * s;
        ctx.beginPath();
        ctx.arc(px, py, 6.5 * s, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.fillStyle = "rgba(255, 183, 74, 0.9)";
        ctx.beginPath();
        ctx.arc(px, py, 2.2 * s, 0, 2 * Math.PI);
        ctx.fill();
      } else {
        // surveyed: solid amber diamond, confirmed intel.
        ctx.save();
        ctx.translate(px, py);
        ctx.rotate(Math.PI / 4);
        ctx.fillStyle = "rgba(255, 200, 90, 0.95)";
        const d = 4.4 * s;
        ctx.fillRect(-d / 2, -d / 2, d, d);
        ctx.restore();
      }
    }

    // ---- Layer 5: fleet sprites ---------------------------------------
    const nowWall = Date.now();
    for (const m of state.fleet.values()) {
      if (m.coords === null) continue;
      const ageMs = nowWall - m.last_updated * 1000;
      if (ageMs > GONE_SPRITE_MS) continue; // previous-run leftovers
      let pos = this.positions.get(m.instance_id);
      if (!pos) {
        pos = { x: m.coords.x, y: m.coords.y, tx: m.coords.x, ty: m.coords.y, lastSeen: nowWall };
        this.positions.set(m.instance_id, pos);
      }
      pos.tx = m.coords.x;
      pos.ty = m.coords.y;
      pos.lastSeen = nowWall;
      pos.x += (pos.tx - pos.x) * moveK;
      pos.y += (pos.ty - pos.y) * moveK;

      const s = this.spriteScale();
      const anchor = this.spritePixel(m.instance_id)!;
      const px = anchor.px;
      const py = anchor.py;
      const dead = ageMs > STALE_SPRITE_MS;
      const busy = m.state !== "free";
      drawSprite(ctx, m.fleet_type, px, py, s, { dead, busy });

      if (state.selectedId === m.instance_id) {
        ctx.strokeStyle = "rgba(255, 183, 74, 0.9)";
        ctx.lineWidth = 1.4 * s;
        ctx.setLineDash([3 * s, 3 * s]);
        ctx.beginPath();
        ctx.arc(px, py, 13 * s, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
    // GC eased positions for sprites gone from the store.
    for (const key of this.positions.keys()) {
      if (!state.fleet.has(key)) this.positions.delete(key);
    }

    // ---- Layer 6: HQ marker -------------------------------------------
    {
      const { px, py } = kmToPixel(0, 0, w, h);
      const s = this.spriteScale() * 0.9;
      ctx.strokeStyle = "rgba(190, 205, 220, 0.5)";
      ctx.lineWidth = 1.2 * s;
      ctx.strokeRect(px - 5 * s, py - 5 * s, 10 * s, 10 * s);
      ctx.font = `${9 * s}px ui-monospace, Menlo, monospace`;
      ctx.fillStyle = "rgba(190, 205, 220, 0.55)";
      ctx.textAlign = "center";
      ctx.fillText("HQ", px, py + 15 * s);
    }
  }
}

// Tactical sprite set: neutral ink strokes with a dark halo for contrast
// against both terrain and fire. Dead units flip to the alarm red.
function drawSprite(
  ctx: CanvasRenderingContext2D,
  type: string,
  px: number,
  py: number,
  s: number,
  opts: { dead: boolean; busy: boolean },
): void {
  ctx.save();
  ctx.translate(px, py);

  const main = opts.dead
    ? "rgba(248, 81, 73, 0.95)"
    : opts.busy
      ? "rgba(235, 242, 250, 0.98)"
      : "rgba(205, 218, 232, 0.9)";
  // Dark halo so sprites read over bright fire.
  ctx.strokeStyle = "rgba(8, 10, 14, 0.75)";
  ctx.lineWidth = 3.4 * s;
  spritePath(ctx, type, s);
  ctx.stroke();
  ctx.strokeStyle = main;
  ctx.lineWidth = 1.5 * s;
  spritePath(ctx, type, s);
  ctx.stroke();

  if (opts.dead) {
    // Kill cross over the sprite.
    ctx.strokeStyle = "rgba(248, 81, 73, 0.95)";
    ctx.lineWidth = 1.6 * s;
    ctx.beginPath();
    ctx.moveTo(-8 * s, -8 * s);
    ctx.lineTo(8 * s, 8 * s);
    ctx.moveTo(8 * s, -8 * s);
    ctx.lineTo(-8 * s, 8 * s);
    ctx.stroke();
  }
  ctx.restore();
}

function spritePath(ctx: CanvasRenderingContext2D, type: string, s: number): void {
  ctx.beginPath();
  switch (type) {
    case "uav":
      // Delta wing.
      ctx.moveTo(0, -7 * s);
      ctx.lineTo(6 * s, 5 * s);
      ctx.lineTo(0, 2.4 * s);
      ctx.lineTo(-6 * s, 5 * s);
      ctx.closePath();
      break;
    case "drone":
      // Quad diamond.
      ctx.moveTo(0, -4.6 * s);
      ctx.lineTo(4.6 * s, 0);
      ctx.lineTo(0, 4.6 * s);
      ctx.lineTo(-4.6 * s, 0);
      ctx.closePath();
      break;
    case "heli":
      // Rotor disc + tail.
      ctx.arc(0, 0, 5 * s, 0, 2 * Math.PI);
      ctx.moveTo(-8 * s, 0);
      ctx.lineTo(8 * s, 0);
      break;
    case "ffunit":
      // Engine block with hose cross.
      ctx.rect(-5 * s, -4 * s, 10 * s, 8 * s);
      ctx.moveTo(-5 * s, -4 * s);
      ctx.lineTo(5 * s, 4 * s);
      break;
    case "medevac":
      // Square with medic cross.
      ctx.rect(-5 * s, -5 * s, 10 * s, 10 * s);
      ctx.moveTo(0, -3 * s);
      ctx.lineTo(0, 3 * s);
      ctx.moveTo(-3 * s, 0);
      ctx.lineTo(3 * s, 0);
      break;
    default:
      ctx.arc(0, 0, 3.5 * s, 0, 2 * Math.PI);
  }
}
