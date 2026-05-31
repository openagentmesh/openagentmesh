import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    testTimeout: 30_000,
    hookTimeout: 30_000,
    // Each test file spawns its own nats-server on a free port, so files are
    // isolated; default parallel file execution is safe.
  },
});
