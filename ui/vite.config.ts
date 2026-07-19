import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vitest/config";

/**
 * Dev-server stand-in for `oam ui`'s `GET /config.json` (ADR-0056): the SPA
 * bootstraps by fetching this and connecting to the returned websocket URL.
 * `oam mesh up` opens the listener on mesh port + 1 (4223 by default);
 * override with OAM_NATS_WS_URL when pointing the dev server elsewhere.
 */
function configJson(): Plugin {
  return {
    name: "oam-config-json",
    configureServer(server) {
      server.middlewares.use("/config.json", (_req, res) => {
        res.setHeader("Content-Type", "application/json");
        res.end(
          JSON.stringify({ nats_ws_url: process.env["OAM_NATS_WS_URL"] ?? "ws://localhost:4223" }),
        );
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), configJson()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});
