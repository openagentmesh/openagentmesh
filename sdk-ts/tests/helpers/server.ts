import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { connect as netConnect, createServer } from "node:net";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

export interface NatsServer {
  url: string;
  port: number;
  stop: () => Promise<void>;
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const addr = srv.address();
      if (addr && typeof addr === "object") {
        const { port } = addr;
        srv.close(() => resolve(port));
      } else {
        srv.close(() => reject(new Error("could not determine free port")));
      }
    });
  });
}

function probe(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const sock = netConnect(port, "127.0.0.1");
    sock.on("connect", () => {
      sock.destroy();
      resolve(true);
    });
    sock.on("error", () => resolve(false));
  });
}

async function waitReady(port: number, proc: ChildProcess): Promise<void> {
  for (let i = 0; i < 100; i++) {
    if (proc.exitCode !== null) throw new Error(`nats-server exited (code ${proc.exitCode})`);
    if (await probe(port)) return;
    await new Promise((r) => setTimeout(r, 50));
  }
  throw new Error("nats-server did not become ready within 5s");
}

/** Spawn a JetStream-enabled nats-server on a free TCP port for the duration of a test suite. */
export async function startNatsServer(): Promise<NatsServer> {
  const bin = process.env.NATS_SERVER_BIN ?? join(homedir(), ".agentmesh", "bin", "nats-server");
  const port = await freePort();
  const store = mkdtempSync(join(tmpdir(), "oam-ts-nats-"));
  const proc = spawn(bin, ["-p", String(port), "-js", "--store_dir", store], {
    stdio: ["ignore", "ignore", "pipe"],
    detached: false,
  });
  proc.stderr?.on("data", () => {}); // drain
  await waitReady(port, proc);

  return {
    url: `nats://127.0.0.1:${port}`,
    port,
    stop: () =>
      new Promise<void>((resolve) => {
        proc.once("exit", () => {
          try {
            rmSync(store, { recursive: true, force: true });
          } catch {
            /* ignore */
          }
          resolve();
        });
        proc.kill("SIGTERM");
        setTimeout(() => proc.kill("SIGKILL"), 3000);
      }),
  };
}
