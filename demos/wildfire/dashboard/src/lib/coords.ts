// Coordinate math for the wildfire scenario UI.
//
// One-for-one TypeScript translation of `demos/wildfire/core/keys.py` plus
// the canvas-pixel <-> world-km projection. The world is bounded
// `[-5, +5]` km on each axis; the 200 m grid is 50x50 cells.
//
// Per D-52 (`.planning/phases/02-cascade-closure/02-CONTEXT.md`) the
// browser sends raw km coords (rounded to 4 decimals) on click; the server
// is the single source of truth for snapping the click to a cell. This
// module therefore owns pixel <-> km conversion AND a TypeScript-side
// `cellIndices` / `cellCenter` (used by `magnitude.ts` to key its per-cell
// click cycle), but does NOT pre-snap clicks before send.

export const WORLD_MIN_KM = -5.0;
export const WORLD_MAX_KM = 5.0;
export const CELL_SIZE_KM = 0.2;
export const GRID_DIM = 50;

/**
 * Snap a world coordinate to its (x_idx, y_idx) cell index.
 *
 * Mirrors `cell_indices` in `demos/wildfire/core/keys.py`:
 * `int((coord + 5.0) / CELL_SIZE_KM)` with both axes clamped to
 * `[0, GRID_DIM - 1]`. Matches Python `int()` semantics for the values
 * we care about (non-negative after the +5.0 shift) via `Math.floor`.
 */
export function cellIndices(x: number, y: number): [number, number] {
  let xi = Math.floor((x - WORLD_MIN_KM) / CELL_SIZE_KM);
  let yi = Math.floor((y - WORLD_MIN_KM) / CELL_SIZE_KM);
  if (xi < 0) xi = 0;
  else if (xi >= GRID_DIM) xi = GRID_DIM - 1;
  if (yi < 0) yi = 0;
  else if (yi >= GRID_DIM) yi = GRID_DIM - 1;
  return [xi, yi];
}

/**
 * Inverse of {@link cellIndices}: return the center of cell
 * `(x_idx, y_idx)` in world km.
 */
export function cellCenter(xi: number, yi: number): { x: number; y: number } {
  return {
    x: WORLD_MIN_KM + (xi + 0.5) * CELL_SIZE_KM,
    y: WORLD_MIN_KM + (yi + 0.5) * CELL_SIZE_KM,
  };
}

/**
 * Project a canvas pixel `(px, py)` (top-left origin) onto world km.
 * Output is rounded to 4 decimal places per D-52.
 */
export function pixelToKm(
  px: number,
  py: number,
  w: number,
  h: number,
): { x: number; y: number } {
  const x = WORLD_MIN_KM + (px / w) * (WORLD_MAX_KM - WORLD_MIN_KM);
  const y = WORLD_MIN_KM + (py / h) * (WORLD_MAX_KM - WORLD_MIN_KM);
  return {
    x: Math.round(x * 10000) / 10000,
    y: Math.round(y * 10000) / 10000,
  };
}

/**
 * Project world km `(x, y)` onto canvas pixel coordinates given the
 * canvas dimensions `(w, h)`.
 */
export function kmToPixel(
  x: number,
  y: number,
  w: number,
  h: number,
): { px: number; py: number } {
  return {
    px: ((x - WORLD_MIN_KM) / (WORLD_MAX_KM - WORLD_MIN_KM)) * w,
    py: ((y - WORLD_MIN_KM) / (WORLD_MAX_KM - WORLD_MIN_KM)) * h,
  };
}
