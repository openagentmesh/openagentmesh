---
phase: 02-cascade-closure
plan: 06
subsystem: dashboard-frontend
tags: [dashboard, frontend, svelte, vite, pnpm, scaffolding, D-25, D-36]
requires:
  - "02-01 (no runtime coupling, but frontend lives in same demo subtree)"
provides:
  - "demos/wildfire/dashboard/ buildable via pnpm install + pnpm run build"
  - "demos/wildfire/dashboard/dist/index.html consumable by the FastAPI dashboard backend (plan 02-05)"
  - "Empty placeholder Svelte root (loading state) so the round-trip works before plan 02-07 wires the canvas"
affects:
  - ".gitignore (added demos/wildfire/dashboard/{node_modules,dist} rules)"
tech_stack:
  added:
    - "svelte 5.55.5"
    - "@sveltejs/vite-plugin-svelte 4.0.4"
    - "@tsconfig/svelte 5.0.8"
    - "svelte-check 4.4.8"
    - "typescript 5.9.3"
    - "vite 5.4.21"
    - "pnpm 9.15.0 (packageManager pin)"
  patterns:
    - "Svelte 5 runes ($state) in App.svelte"
    - "Vite emptyOutDir: false plus dist/.gitkeep (mirrors ui/vite.config.ts)"
    - "svelte-check + vite build in package.json build script"
key_files:
  created:
    - "demos/wildfire/dashboard/package.json"
    - "demos/wildfire/dashboard/pnpm-lock.yaml"
    - "demos/wildfire/dashboard/tsconfig.json"
    - "demos/wildfire/dashboard/vite.config.ts"
    - "demos/wildfire/dashboard/svelte.config.js"
    - "demos/wildfire/dashboard/index.html"
    - "demos/wildfire/dashboard/src/main.ts"
    - "demos/wildfire/dashboard/src/App.svelte"
    - "demos/wildfire/dashboard/src/app.css"
    - "demos/wildfire/dashboard/src/vite-env.d.ts"
    - "demos/wildfire/dashboard/dist/.gitkeep"
  modified:
    - ".gitignore"
decisions:
  - "Use emptyOutDir: false in vite.config.ts so the tracked dist/.gitkeep survives builds. Identical pattern to ui/vite.config.ts (Phase 1 plan 01-09 deviation)."
  - "Pin packageManager to pnpm@9.15.0 (not 9.0.0) because Corepack in this environment ships pnpm 11.0.9 which segfaults on Node 20 (ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING). 9.15.0 is the stable LTS-equivalent line and matches what corepack prepare resolved cleanly."
  - "Use port 5174 for vite dev (port 5173 is taken by the existing ui/ admin UI). Build output is independent of the dev port."
metrics:
  duration: "single executor session"
  completed: "2026-05-09"
  tasks: 2
  files_created: 11
  files_modified: 1
---

# Phase 02 Plan 06: Dashboard Frontend Scaffold Summary

Svelte 5 + Vite + TypeScript scaffold for the wildfire scenario UI dashboard at `demos/wildfire/dashboard/`. `pnpm install && pnpm run build` produces a `dist/index.html` that the FastAPI backend (plan 02-05) can serve. The Svelte component tree is intentionally minimal: a placeholder root that says "Wildfire scenario UI / loading..." so the browser to FastAPI to Svelte round-trip works end-to-end before plan 02-07 wires the canvas + click cycle + WebSocket client.

## Tasks Executed

| Task | Name                                              | Commit  |
| ---- | ------------------------------------------------- | ------- |
| 1    | Scaffold Svelte 5 + Vite + TypeScript project     | 89c3bfd |
| 2    | Update .gitignore for the second pnpm project     | 31d3f58 |

## Resolved Package Versions

`pnpm install` resolved the loose `^` ranges in `package.json` to:

| Package                          | Spec       | Resolved |
| -------------------------------- | ---------- | -------- |
| svelte                           | `^5.0.0`   | 5.55.5   |
| @sveltejs/vite-plugin-svelte     | `^4.0.0`   | 4.0.4    |
| @tsconfig/svelte                 | `^5.0.0`   | 5.0.8    |
| svelte-check                     | `^4.0.0`   | 4.4.8    |
| typescript                       | `^5.5.0`   | 5.9.3    |
| vite                             | `^5.4.0`   | 5.4.21   |

These are the versions captured in `pnpm-lock.yaml`. A clean clone reinstall will be deterministic via the lockfile.

## emptyOutDir Decision

Chose `emptyOutDir: false` in `vite.config.ts`. Reason: a `dist/.gitkeep` is tracked so a fresh clone has the directory present in git (the same pattern Phase 1 plan 01-09 used for `src/openagentmesh/_ui_assets/.gitkeep`). With `emptyOutDir: true`, Vite would wipe the placeholder on every build, leaving the directory absent on a fresh clone until the first build runs — which would also defeat the gitignore exemption. Stale build artifacts from previous builds are fine because `dist/*` is gitignored.

## .gitignore Additions

Appended a "Wildfire dashboard frontend" section after the existing "Frontend build artifacts" block:

```
# Wildfire dashboard frontend (D-25, D-36)
demos/wildfire/dashboard/node_modules/
demos/wildfire/dashboard/dist/*
!demos/wildfire/dashboard/dist/.gitkeep
```

Verified `git check-ignore` matches the rules and `git ls-files demos/wildfire/dashboard/dist/.gitkeep` returns the path (the exemption works).

## Verification

- `cd demos/wildfire/dashboard && pnpm install && pnpm run build` exits 0; `svelte-check` reports `0 ERRORS 0 WARNINGS`; `vite build` produces `dist/index.html`, `dist/assets/index-*.css`, `dist/assets/index-*.js`.
- `dist/index.html` contains `<div id="app"></div>` (the Svelte mount point), so plan 02-07 can mount over it.
- `git status --short demos/wildfire/dashboard/` is clean after a build (build output is ignored).
- Regression: `uv run pytest tests/wildfire/unit -x -q` passes 152 tests. Phase 1 + earlier Phase 2 Python untouched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pin packageManager to pnpm@9.15.0, not 9.0.0**

- **Found during:** Task 1 setup
- **Issue:** The plan body suggested `"packageManager": "pnpm@9.0.0"` (matching the existing `ui/` admin UI). However, `corepack` on this environment defaults to pnpm 11.0.9, which crashes on Node 20.19 with `ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING`. Without an explicit pin to a known-good version, `pnpm install` would fail.
- **Fix:** Pin `packageManager` to `pnpm@9.15.0` (a stable 9.x point release that runs cleanly on Node 20). `corepack prepare pnpm@9.15.0 --activate` was used to activate it for the build. The `ui/` project's `pnpm@9.0.0` pin remains untouched (different project, different lockfile). Plan-level guidance ("a minor diff is acceptable") explicitly allows this.
- **Files modified:** demos/wildfire/dashboard/package.json
- **Commit:** 89c3bfd

**2. [Rule 2 - Robustness] Guard #app mount point in main.ts**

- **Found during:** Task 1 implementation
- **Issue:** The plan's example `main.ts` used `document.getElementById("app")!` (non-null assertion). With `strict: true` + `verbatimModuleSyntax: true` in `tsconfig.json`, TypeScript accepts the `!` but it silently produces a runtime `mount(target: null)` if the index.html is corrupted by a bundler bug. svelte-check passes either way.
- **Fix:** Replaced the non-null assertion with an explicit guard that throws a descriptive error if the mount point is missing. This is the same pattern Phase 1's `ui/src/main.tsx` uses for `#root`, and is harmless for the placeholder use case.
- **Files modified:** demos/wildfire/dashboard/src/main.ts
- **Commit:** 89c3bfd

**3. [Rule 3 - Blocking] Vite dev port set to 5174**

- **Found during:** Task 1 vite.config.ts authoring
- **Issue:** The plan's vite.config.ts example did not specify a `server.port`. Vite defaults to 5173, which is already claimed by the `ui/` admin UI dev server (per `ui/vite.config.ts`). Running both dev servers concurrently would collide.
- **Fix:** Set `server.port: 5174`. Build output is independent of dev port; this only affects `pnpm run dev`. plan 02-07 may revisit if it wants to align with a specific port for cross-origin testing.
- **Files modified:** demos/wildfire/dashboard/vite.config.ts
- **Commit:** 89c3bfd

These deviations are all small and within the plan's stated tolerance ("a minor diff is acceptable"). No architectural changes; no Rule 4 escalation needed.

## Hand-off Notes

### To plan 02-07 (canvas + WS client)

The placeholder `App.svelte` is a single `<main>` with a `<h1>` and a `<p>`. Plan 02-07 should replace it wholesale (not extend it) with the real component tree. Files plan 02-07 must create:

- `demos/wildfire/dashboard/src/lib/canvas.ts` — pure rendering helpers (cell -> color, draw frame).
- `demos/wildfire/dashboard/src/lib/mesh.ts` — WebSocket client that connects to the dashboard backend's `/ws` endpoint (FastAPI bridge from plan 02-05) and exposes a Svelte store of cell state.
- `demos/wildfire/dashboard/src/lib/magnitude.ts` — click-to-magnitude state machine (per the dashboard spec's click cycle: -2 -> -1 -> +1 -> +2 -> -2 ...).

`tsconfig.json` already includes `src/**/*.ts`, so any `src/lib/*.ts` files are picked up by `svelte-check` automatically.

### To plan 02-09 (orchestrator + integration)

The orchestrator must run `pnpm run build` once before first dashboard boot, mirroring the Phase 1 admin UI pattern (`tests/wildfire/integration/test_phase1_cascade.py:_ensure_ui_built`). Suggested helper:

```python
def _ensure_dashboard_built() -> None:
    dashboard_dir = REPO_ROOT / "demos" / "wildfire" / "dashboard"
    index_html = dashboard_dir / "dist" / "index.html"
    if index_html.exists():
        return
    subprocess.run(["pnpm", "install"], cwd=dashboard_dir, check=True)
    subprocess.run(["pnpm", "run", "build"], cwd=dashboard_dir, check=True)
```

The dashboard backend (plan 02-05) should serve `demos/wildfire/dashboard/dist/` as static; the file path is stable across builds because Vite always writes `index.html` at the root and asset hashes are referenced from it.

## Self-Check: PASSED

Verified all claims:

- demos/wildfire/dashboard/package.json: FOUND
- demos/wildfire/dashboard/pnpm-lock.yaml: FOUND
- demos/wildfire/dashboard/tsconfig.json: FOUND
- demos/wildfire/dashboard/vite.config.ts: FOUND
- demos/wildfire/dashboard/svelte.config.js: FOUND
- demos/wildfire/dashboard/index.html: FOUND
- demos/wildfire/dashboard/src/main.ts: FOUND
- demos/wildfire/dashboard/src/App.svelte: FOUND
- demos/wildfire/dashboard/src/app.css: FOUND
- demos/wildfire/dashboard/src/vite-env.d.ts: FOUND
- demos/wildfire/dashboard/dist/.gitkeep: FOUND (git ls-files confirms tracked)
- Commit 89c3bfd: FOUND in git log
- Commit 31d3f58: FOUND in git log
- pnpm run build: exits 0, produces dist/index.html with `<div id="app"></div>` mount point
- uv run pytest tests/wildfire/unit -x -q: 152 passed (Python regression clean)
