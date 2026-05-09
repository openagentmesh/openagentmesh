import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/openagentmesh/_ui_assets",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
  },
});
