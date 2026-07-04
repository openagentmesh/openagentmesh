// Procedural terrain skin for the wildfire canvas.
//
// Seeded value-noise fBm rendered ONCE to an offscreen canvas: elevation
// shading (NW hillshade) under a vegetation tint, dark and desaturated so
// the fire severity ramp stays the only loud color on screen. No map
// tiles, no network fetches, no dependencies; same seed -> same terrain,
// which keeps the demo recording reproducible.

// Mulberry32: tiny deterministic PRNG, good enough for terrain.
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Value-noise lattice: GRID x GRID random values, bilinear + smoothstep
// interpolation between lattice points.
class ValueNoise {
  private lattice: Float32Array;
  private dim: number;

  constructor(seed: number, dim = 64) {
    this.dim = dim;
    const rand = mulberry32(seed);
    this.lattice = new Float32Array(dim * dim);
    for (let i = 0; i < this.lattice.length; i++) this.lattice[i] = rand();
  }

  private at(ix: number, iy: number): number {
    const d = this.dim;
    // Wrap so sampling never walks off the lattice.
    return this.lattice[((iy % d) + d) % d * d + (((ix % d) + d) % d)];
  }

  sample(x: number, y: number): number {
    const ix = Math.floor(x);
    const iy = Math.floor(y);
    const fx = x - ix;
    const fy = y - iy;
    const sx = fx * fx * (3 - 2 * fx);
    const sy = fy * fy * (3 - 2 * fy);
    const v00 = this.at(ix, iy);
    const v10 = this.at(ix + 1, iy);
    const v01 = this.at(ix, iy + 1);
    const v11 = this.at(ix + 1, iy + 1);
    const top = v00 + sx * (v10 - v00);
    const bot = v01 + sx * (v11 - v01);
    return top + sy * (bot - top);
  }
}

// fBm: 5 octaves of value noise.
function fbm(noise: ValueNoise, x: number, y: number): number {
  let amp = 0.5;
  let freq = 1;
  let sum = 0;
  let norm = 0;
  for (let o = 0; o < 5; o++) {
    sum += amp * noise.sample(x * freq, y * freq);
    norm += amp;
    amp *= 0.55;
    freq *= 2;
  }
  return sum / norm;
}

// Ridged multifractal: sharp crests where value noise folds, for actual
// relief instead of soft fog.
function ridged(noise: ValueNoise, x: number, y: number): number {
  let amp = 0.55;
  let freq = 1;
  let sum = 0;
  let norm = 0;
  for (let o = 0; o < 4; o++) {
    const n = noise.sample(x * freq, y * freq);
    sum += amp * (1 - Math.abs(2 * n - 1));
    norm += amp;
    amp *= 0.5;
    freq *= 2.1;
  }
  return sum / norm;
}

/**
 * Render the terrain to an offscreen canvas of `w` x `h` device pixels.
 * Call once per resize; drawing it per-frame is a single drawImage.
 */
export function renderTerrain(w: number, h: number, seed: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return canvas;

  const elevNoise = new ValueNoise(seed, 64);
  const vegNoise = new ValueNoise(seed ^ 0x9e3779b9, 64);

  // Sample at one-third resolution and let the browser upscale: full-res
  // fBm at 1920x1080 is ~8M samples, too slow at boot.
  const sw = Math.max(1, Math.floor(w / 3));
  const sh = Math.max(1, Math.floor(h / 3));
  const img = ctx.createImageData(sw, sh);
  const data = img.data;

  const SCALE = 11.0; // world-noise frequency across the map
  const EPS = 0.22; // gradient step for hillshade, in lattice units

  for (let py = 0; py < sh; py++) {
    for (let px = 0; px < sw; px++) {
      const nx = (px / sw) * SCALE;
      const ny = (py / sh) * SCALE;

      // Elevation: soft fBm base folded with ridged crests so the map has
      // actual landforms, not fog.
      const elevAt = (ax: number, ay: number): number =>
        0.55 * fbm(elevNoise, ax, ay) + 0.45 * ridged(elevNoise, ax * 0.6 + 7.3, ay * 0.6 + 2.9);
      const e = elevAt(nx, ny);
      // NW hillshade: gradient against light from the top-left.
      const ex = elevAt(nx + EPS, ny) - elevAt(nx - EPS, ny);
      const ey = elevAt(nx, ny + EPS) - elevAt(nx, ny - EPS);
      const shade = Math.max(-1, Math.min(1, (ex + ey) * 4.2));

      const veg = fbm(vegNoise, nx * 1.4, ny * 1.4);

      // Base: dark earth. Vegetation pulls toward muted conifer green,
      // elevation lightens ridges, hillshade carves the relief.
      // All values stay low-luminance so ember tones dominate later.
      let r = 24 + e * 26;
      let g = 28 + e * 30;
      let b = 24 + e * 20;
      // Vegetation clumps: valleys and lowlands greener, thinning on ridges.
      const vegMix = Math.max(0, veg - 0.3) * (1.15 - e * 0.8);
      r += vegMix * -10;
      g += vegMix * 26;
      b += vegMix * 2;
      // Hillshade: darken SE-facing, lighten NW-facing slopes.
      const light = 1 - shade * 0.55;
      r *= light;
      g *= light;
      b *= light;

      const i = (py * sw + px) * 4;
      data[i] = Math.max(0, Math.min(255, r));
      data[i + 1] = Math.max(0, Math.min(255, g));
      data[i + 2] = Math.max(0, Math.min(255, b));
      data[i + 3] = 255;
    }
  }

  // Draw the low-res field, then upscale to full size with smoothing.
  const small = document.createElement("canvas");
  small.width = sw;
  small.height = sh;
  small.getContext("2d")?.putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(small, 0, 0, w, h);

  // Faint 1km graticule: tactical map feel without shouting.
  ctx.strokeStyle = "rgba(180, 200, 220, 0.05)";
  ctx.lineWidth = 1;
  const kmLines = 10; // world is 10km across
  for (let i = 1; i < kmLines; i++) {
    const x = (i / kmLines) * w;
    const y = (i / kmLines) * h;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  // Slight vignette to pull the eye inward on video.
  const grad = ctx.createRadialGradient(
    w / 2, h / 2, Math.min(w, h) * 0.45,
    w / 2, h / 2, Math.max(w, h) * 0.75,
  );
  grad.addColorStop(0, "rgba(0,0,0,0)");
  grad.addColorStop(1, "rgba(4,6,8,0.5)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  return canvas;
}
