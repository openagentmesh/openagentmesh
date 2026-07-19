import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { HandlerError, MeshError } from "@openagentmesh/sdk";
import type { StreamOptions } from "@openagentmesh/sdk";
import App from "../src/App";
import { MeshProvider } from "../src/MeshProvider";
import type { MeshClient } from "../src/mesh";
import { AUDIT_LOG, fakeMesh, pushableQueue, REINDEXER, TICKER, TRANSLATOR } from "./fakes";

function renderAt(path: string, client: MeshClient = fakeMesh()): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <MeshProvider client={client}>
        <App />
      </MeshProvider>
    </MemoryRouter>,
  );
}

describe("invocation sandbox", () => {
  it("renders a form field per input-schema property", async () => {
    renderAt("/agents/translator");
    expect(await screen.findByRole("textbox", { name: /text/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /target_lang/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^call$/i })).toBeInTheDocument();
  });

  it("submits the form and renders the call reply", async () => {
    const call = vi.fn().mockResolvedValue({ translated: "Bonjour" });
    renderAt("/agents/translator", fakeMesh([TRANSLATOR], { call }));
    await userEvent.type(await screen.findByRole("textbox", { name: /text/i }), "Hello");
    await userEvent.type(screen.getByRole("textbox", { name: /target_lang/i }), "fr");
    await userEvent.click(screen.getByRole("button", { name: /^call$/i }));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith("translator", { text: "Hello", target_lang: "fr" }),
    );
    expect(await screen.findByText(/"Bonjour"/)).toBeInTheDocument();
  });

  it("invokes a no-input trigger agent via a bare call button", async () => {
    const call = vi.fn().mockResolvedValue({ indexed: 42 });
    renderAt("/agents/reindexer", fakeMesh([REINDEXER], { call }));
    await userEvent.click(await screen.findByRole("button", { name: /^call$/i }));
    await waitFor(() => expect(call).toHaveBeenCalledTimes(1));
    expect(call.mock.calls[0]?.[0]).toBe("reindexer");
    expect(await screen.findByText(/"indexed": 42/)).toBeInTheDocument();
  });

  it("shows no invoke panel for a source-only agent", async () => {
    renderAt("/agents/audit-log", fakeMesh([AUDIT_LOG]));
    await screen.findByText("mesh.agent.audit-log");
    expect(screen.queryByText(/invoke/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^(call|stream)$/i })).not.toBeInTheDocument();
  });

  it("renders stream chunks live and reports completion", async () => {
    const q = pushableQueue();
    const stream = vi.fn((_name: string, _payload?: unknown, opts?: StreamOptions) =>
      q.iterate(opts?.signal),
    );
    renderAt("/agents/ticker", fakeMesh([TICKER], { stream }));
    await userEvent.click(await screen.findByRole("button", { name: /^stream$/i }));
    q.push({ price: 101 });
    expect(await screen.findByText(/"price": 101/)).toBeInTheDocument();
    q.push({ price: 102 });
    expect(await screen.findByText(/"price": 102/)).toBeInTheDocument();
    q.end();
    expect(await screen.findByText(/2 chunks/i)).toBeInTheDocument();
    expect(screen.getByText(/done/i)).toBeInTheDocument();
  });

  it("stops a running stream from the stop button", async () => {
    const q = pushableQueue();
    const stream = vi.fn((_name: string, _payload?: unknown, opts?: StreamOptions) =>
      q.iterate(opts?.signal),
    );
    renderAt("/agents/ticker", fakeMesh([TICKER], { stream }));
    await userEvent.click(await screen.findByRole("button", { name: /^stream$/i }));
    q.push({ price: 101 });
    await screen.findByText(/"price": 101/);
    await userEvent.click(screen.getByRole("button", { name: /stop/i }));
    expect(await screen.findByText(/stopped/i)).toBeInTheDocument();
    expect(screen.getByText(/1 chunk/i)).toBeInTheDocument();
  });

  it("renders the error envelope from a failed call, including not_available", async () => {
    const call = vi
      .fn()
      .mockRejectedValue(
        new MeshError("agent 'translator' is registered but not currently available", {
          code: "not_available",
          agent: "translator",
        }),
      );
    renderAt("/agents/translator", fakeMesh([TRANSLATOR], { call }));
    await userEvent.type(await screen.findByRole("textbox", { name: /text/i }), "Hello");
    await userEvent.type(screen.getByRole("textbox", { name: /target_lang/i }), "fr");
    await userEvent.click(screen.getByRole("button", { name: /^call$/i }));
    expect(await screen.findByText("not_available")).toBeInTheDocument();
    expect(
      screen.getByText(/registered but not currently available/i),
    ).toBeInTheDocument();
    // Gate-closed errors are retryable (concepts/lifecycle.md) — the sandbox says so.
    expect(screen.getByText(/retry/i)).toBeInTheDocument();
  });

  it("renders a mid-stream error envelope and keeps received chunks", async () => {
    const q = pushableQueue();
    const stream = vi.fn((_name: string, _payload?: unknown, opts?: StreamOptions) =>
      q.iterate(opts?.signal),
    );
    renderAt("/agents/ticker", fakeMesh([TICKER], { stream }));
    await userEvent.click(await screen.findByRole("button", { name: /^stream$/i }));
    q.push({ price: 101 });
    await screen.findByText(/"price": 101/);
    q.fail(new HandlerError("feed exploded", { agent: "ticker" }));
    expect(await screen.findByText("handler_error")).toBeInTheDocument();
    expect(screen.getByText(/feed exploded/i)).toBeInTheDocument();
    expect(screen.getByText(/"price": 101/)).toBeInTheDocument();
  });
});
