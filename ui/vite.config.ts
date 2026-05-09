import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/openagentmesh/_ui_assets",
    // emptyOutDir would wipe the tracked .gitkeep (which keeps the assets
    // directory present in git so oam ui's index-not-found check is the only
    // failure mode for missing-bundle, not directory-not-found). We leave
    // stale build artifacts in place; gitignore covers them.
    emptyOutDir: false,
  },
  server: {
    port: 5173,
  },
});
