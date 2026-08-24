// Per-cell click cycle state for the dashboard canvas (D-49 / D-50).
//
// The cycle lives entirely in browser memory. The backend has no awareness
// of "the cycle" — it only sees individual `{type: "click", coords,
// temperature}` frames and writes (or deletes) the corresponding KV cell.
// The cycle is therefore stateless from the server's perspective; this
// module exists so the same cell increases in magnitude on repeated
// clicks without forcing the operator to enter a number.
//
// Cycle:
//
//   off (delete)  ->  small (200°C)  ->  medium (500°C)  ->  large (800°C)
//                  ^                                                    |
//                  +----------------------------------------------------+
//
// Magnitudes mirror `core/config.py` `SPAWN_MAGNITUDE_SMALL/_MEDIUM/_LARGE`.
// They're hardcoded here because Phase 2 ships without a JSON-config
// endpoint (Phase 5+ polish). If the Python constants change, this file
// must be updated by hand.
//
// Keying is by `(x_idx, y_idx)` rather than raw coords so two clicks on
// nearby pixels inside the same 200 m cell hit the same cycle entry —
// matching server-side grid snapping (D-52).

import { cellIndices } from "./coords";

export const SPAWN_MAGNITUDE_SMALL = 200.0;
export const SPAWN_MAGNITUDE_MEDIUM = 500.0;
export const SPAWN_MAGNITUDE_LARGE = 800.0;

export type MagnitudeState = "off" | "small" | "medium" | "large";

const cellState = new Map<string, MagnitudeState>();

function key(xi: number, yi: number): string {
  return `${xi}:${yi}`;
}

/**
 * Advance the cycle for the cell containing world coords `(x, y)` and
 * return the next state plus the temperature payload to send.
 *
 * `temperature` is `null` on the "off" transition: the server will
 * `mesh.kv.delete` the cell key (sparse-KV invariant per D-50).
 */
export function advance(
  x: number,
  y: number,
): { state: MagnitudeState; temperature: number | null } {
  const [xi, yi] = cellIndices(x, y);
  const k = key(xi, yi);
  const cur = cellState.get(k) ?? "off";
  const next: MagnitudeState =
    cur === "off"
      ? "small"
      : cur === "small"
        ? "medium"
        : cur === "medium"
          ? "large"
          : "off";
  cellState.set(k, next);

  const temperature =
    next === "small"
      ? SPAWN_MAGNITUDE_SMALL
      : next === "medium"
        ? SPAWN_MAGNITUDE_MEDIUM
        : next === "large"
          ? SPAWN_MAGNITUDE_LARGE
          : null;

  return { state: next, temperature };
}

/**
 * Reset the cycle for the cell containing `(x, y)` to "off". Used when a
 * `cell_delete` envelope arrives from the server (someone else, or the
 * same browser at a previous tick, removed this cell): the next click
 * should start at "small" again.
 */
export function reset(x: number, y: number): void {
  const [xi, yi] = cellIndices(x, y);
  cellState.set(key(xi, yi), "off");
}

/**
 * Reset the cycle for cell index `(x_idx, y_idx)` directly. Convenience
 * for callers that already have grid indices (e.g. the WebSocket
 * dispatcher for `cell_delete`).
 */
export function resetIdx(xIdx: number, yIdx: number): void {
  cellState.set(key(xIdx, yIdx), "off");
}

/**
 * Inspect the current cycle state for the cell containing `(x, y)`.
 */
export function getState(x: number, y: number): MagnitudeState {
  const [xi, yi] = cellIndices(x, y);
  return cellState.get(key(xi, yi)) ?? "off";
}
