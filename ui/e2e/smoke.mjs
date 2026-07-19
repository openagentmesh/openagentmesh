/**
 * Admin-UI smoke e2e (ADR-0056 wave 5).
 *
 * The only automated coverage of the real browser transport: jsdom unit tests
 * inject a fake mesh client, so connect / config.json bootstrap / KV watch /
 * request-reply over a real websocket are exercised nowhere else.
 *
 * Drives the PRODUCTION build (ui/dist) served by a real `oam ui` against a
 * real `oam mesh up`, in a throwaway working directory:
 *
 *   1. registry shows the e2e host's agent with a live status dot
 *   2. invocation sandbox: rjsf form from the input schema, Call round-trip
 *   3. event feed: subscribe on `mesh.>` sees live mesh traffic
 *   4. zero page errors anywhere along the way
 *
 * Prereqs: `pnpm run build` (ui/dist must exist), `uv sync` at the repo root,
 * and a chromium for playwright — either `npx playwright install chromium`
 * or OAM_E2E_CHROMIUM pointing at a chromium binary.
 *
 * Run: `pnpm run e2e` (from ui/), or `node ui/e2e/smoke.mjs` from the root.
 */

import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const DIST = join(ROOT, "ui", "dist");
const MESH_PORT = Number(process.env.OAM_E2E_MESH_PORT ?? 4290);
const WS_PORT = MESH_PORT + 1; // oam mesh up opens the websocket listener on port + 1
const UI_PORT = MESH_PORT + 3;
const MESH_URL = `nats://127.0.0.1:${MESH_PORT}`;

const children = [];
let workDir;

function fail(message) {
  console.error(`FAIL: ${message}`);
  cleanup();
  process.exit(1);
}

function cleanup() {
  for (const child of children.reverse()) {
    if (child.exitCode === null) child.kill("SIGTERM");
  }
  if (workDir) rmSync(workDir, { recursive: true, force: true });
}

/** Spawn a child and resolve once `marker` appears on stdout/stderr. */
function spawnUntil(label, command, args, marker, { env = {}, timeoutMs = 60_000 } = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd: workDir,
      env: { ...process.env, ...env },
      stdio: ["ignore", "pipe", "pipe"],
    });
    children.push(child);
    let output = "";
    const timer = setTimeout(() => {
      reject(new Error(`${label}: timed out waiting for "${marker}". Output so far:\n${output}`));
    }, timeoutMs);
    const onData = (chunk) => {
      output += chunk.toString();
      if (output.includes(marker)) {
        clearTimeout(timer);
        resolvePromise({ child, output });
      }
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
    child.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`${label}: exited with ${code} before "${marker}". Output:\n${output}`));
    });
  });
}

async function main() {
  if (!existsSync(join(DIST, "index.html"))) {
    fail(`no production build at ${DIST} — run \`pnpm run build\` in ui/ first`);
  }
  workDir = mkdtempSync(join(tmpdir(), "oam-ui-e2e-"));

  console.log(`mesh up on ${MESH_PORT} (ws ${WS_PORT})...`);
  await spawnUntil(
    "oam mesh up",
    "uv",
    ["run", "--project", ROOT, "oam", "mesh", "up", "--port", String(MESH_PORT), "--foreground"],
    "WebSocket listener",
  );

  console.log("starting e2e agent host...");
  await spawnUntil(
    "e2e host",
    "uv",
    ["run", "--project", ROOT, "python", join(ROOT, "ui", "e2e", "host.py")],
    "E2E-HOST-READY",
    { env: { OAM_URL: MESH_URL } },
  );

  console.log("starting oam ui...");
  const { output: uiOutput } = await spawnUntil(
    "oam ui",
    "uv",
    [
      "run", "--project", ROOT, "oam", "ui",
      "--port", String(UI_PORT),
      "--url", MESH_URL,
      "--nats-ws-url", `ws://127.0.0.1:${WS_PORT}`,
      "--assets-dir", DIST,
    ],
    "Admin UI running at",
  );
  const uiUrl = uiOutput.match(/Admin UI running at (\S+)/)[1];
  console.log(`ui at ${uiUrl}`);

  const browser = await chromium.launch({
    executablePath: process.env.OAM_E2E_CHROMIUM || undefined,
  });
  const page = await browser.newPage();
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));

  // 1. Registry: agent row present, status dot live (real KV watch + instancesWatch).
  console.log("checking registry...");
  await page.goto(uiUrl, { waitUntil: "networkidle" });
  await page.waitForSelector("tr:has-text('echo')", { timeout: 15_000 });
  await page.waitForSelector('[data-testid="status-echo"][data-live="true"]', {
    timeout: 15_000,
  });

  // 2. Invocation sandbox: rjsf form from the real Pydantic schema, Call round-trip.
  console.log("checking invocation sandbox...");
  await page.goto(`${uiUrl}/agents/echo`, { waitUntil: "networkidle" });
  const textInput = page.locator('input[id$="text"]').first();
  await textInput.waitFor({ timeout: 15_000 });
  await textInput.fill("smoke test");
  await page.getByRole("button", { name: "Call", exact: true }).click();
  await page.waitForSelector("text=smoke test", { timeout: 15_000 });

  // 3. Event feed: subscribing on the default `mesh.>` sees the host's self-call traffic.
  console.log("checking event feed...");
  await page.goto(`${uiUrl}/events`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Subscribe" }).click();
  await page.waitForSelector("text=mesh.agent.echo", { timeout: 15_000 });

  await browser.close();

  if (pageErrors.length > 0) {
    fail(`page errors:\n${pageErrors.join("\n")}`);
  }
  console.log("PASS: registry + sandbox + event feed, zero page errors");
  cleanup();
  process.exit(0);
}

main().catch((err) => fail(err.stack ?? String(err)));
