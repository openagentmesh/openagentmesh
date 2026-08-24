import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  build: {
    outDir: "./dist",
    // Keep dist/.gitkeep so a fresh clone has the directory present in git;
    // emptyOutDir would wipe it on each build. Stale build artifacts are fine
    // because dist/* is gitignored. Mirrors the deviation noted in
    // ui/vite.config.ts (Phase 1 plan 01-09).
    emptyOutDir: false,
  },
  server: {
    port: 5174,
  },
});
