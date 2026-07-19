import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import App from "../src/App";
import { MeshProvider } from "../src/MeshProvider";
import type { MeshClient } from "../src/mesh";
import { fakeMesh } from "./fakes";

function renderApp(client: MeshClient, initialEntries: string[] = ["/"]): ReactNode {
  render(
    <MemoryRouter initialEntries={initialEntries}>
      <MeshProvider client={client}>
        <App />
      </MeshProvider>
    </MemoryRouter>,
  );
  return null;
}

describe("registry screen", () => {
  it("lists each catalog entry with its name", async () => {
    renderApp(fakeMesh());
    expect(await screen.findByText("translator")).toBeInTheDocument();
    expect(screen.getByText("ticker")).toBeInTheDocument();
  });

  it("shows only the first sentence of the description", async () => {
    renderApp(fakeMesh());
    expect(await screen.findByText("Translate text between languages.")).toBeInTheDocument();
    expect(screen.queryByText(/Uses an LLM under the hood/)).not.toBeInTheDocument();
  });

  it("shows capability badges from the catalog flags", async () => {
    renderApp(fakeMesh());
    const translatorRow = (await screen.findByText("translator")).closest("tr");
    const tickerRow = screen.getByText("ticker").closest("tr");
    expect(translatorRow).not.toBeNull();
    expect(tickerRow).not.toBeNull();
    expect(translatorRow!).toHaveTextContent("call");
    expect(tickerRow!).toHaveTextContent("stream");
  });

  it("shows an empty state when no agents are registered", async () => {
    renderApp(fakeMesh([]));
    expect(await screen.findByText(/no agents registered/i)).toBeInTheDocument();
  });

  it("navigates to the agent detail when a row is clicked", async () => {
    renderApp(fakeMesh());
    await userEvent.click(await screen.findByText("translator"));
    expect(await screen.findByText("mesh.agent.translator")).toBeInTheDocument();
  });
});

describe("connection badge", () => {
  it("reports connected when a client is available", async () => {
    renderApp(fakeMesh());
    expect(await screen.findByText("connected")).toBeInTheDocument();
  });
});
