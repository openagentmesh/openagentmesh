import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../src/App";
import { MeshProvider } from "../src/MeshProvider";
import type { MeshClient } from "../src/mesh";
import { fakeMesh } from "./fakes";

function renderAt(path: string, client: MeshClient = fakeMesh()): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <MeshProvider client={client}>
        <App />
      </MeshProvider>
    </MemoryRouter>,
  );
}

describe("agent detail screen", () => {
  it("renders the contract's descriptive fields", async () => {
    renderAt("/agents/translator");
    expect(
      await screen.findByText("Translate text between languages. Uses an LLM under the hood."),
    ).toBeInTheDocument();
    expect(screen.getByText("mesh.agent.translator")).toBeInTheDocument();
    expect(screen.getByText("1.2.0")).toBeInTheDocument();
    expect(screen.getByText("nlp")).toBeInTheDocument();
    expect(screen.getByText("demo")).toBeInTheDocument();
  });

  it("renders input and output schemas", async () => {
    renderAt("/agents/translator");
    expect(await screen.findByText(/input schema/i)).toBeInTheDocument();
    expect(screen.getByText(/output schema/i)).toBeInTheDocument();
    // Schema bodies are pretty-printed JSON containing the property names.
    expect(screen.getByText(/"target_lang"/)).toBeInTheDocument();
    expect(screen.getByText(/"translated"/)).toBeInTheDocument();
  });

  it("renders the chunk schema for streaming agents", async () => {
    renderAt("/agents/ticker");
    expect(await screen.findByText(/chunk schema/i)).toBeInTheDocument();
    expect(screen.getByText(/"price"/)).toBeInTheDocument();
  });

  it("toggles to the raw contract JSON view", async () => {
    renderAt("/agents/translator");
    await screen.findByText("mesh.agent.translator");
    await userEvent.click(screen.getByRole("button", { name: /json/i }));
    expect(screen.getByText(/"skills"/)).toBeInTheDocument();
    expect(screen.getByText(/"registeredAt"/)).toBeInTheDocument();
  });

  it("shows a not-found message for an unknown agent", async () => {
    renderAt("/agents/ghost");
    expect(await screen.findByText(/not found/i)).toBeInTheDocument();
  });
});
