import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { InstancesSnapshot, TapEvent } from "@openagentmesh/sdk";
import App from "../src/App";
import { MeshProvider } from "../src/MeshProvider";
import type { MeshClient } from "../src/mesh";
import { fakeMesh, pushableQueue } from "./fakes";

function renderRegistry(client: MeshClient) {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <MeshProvider client={client}>
        <App />
      </MeshProvider>
    </MemoryRouter>,
  );
}

function livenessFake() {
  const instances = pushableQueue<InstancesSnapshot>();
  const deaths = pushableQueue<TapEvent>();
  const client = fakeMesh(undefined, {
    instancesWatch: (opts) => instances.iterate(opts?.signal),
    tap: (subject, opts) => {
      if (subject !== "mesh.death.>") throw new Error(`unexpected tap('${subject}') in liveness test`);
      return deaths.iterate(opts?.signal);
    },
  });
  return { instances, deaths, client };
}

describe("registry liveness dots", () => {
  it("renders no status dots before the first instances snapshot", async () => {
    const { client } = livenessFake();
    renderRegistry(client);
    await screen.findByText("translator");
    expect(screen.queryByTestId("status-translator")).not.toBeInTheDocument();
  });

  it("shows live for agents served by an instance and offline for the rest", async () => {
    const { instances, client } = livenessFake();
    renderRegistry(client);
    await screen.findByText("translator");

    instances.push({ "host-1": ["translator"] });
    await waitFor(() => {
      expect(screen.getByTestId("status-translator")).toHaveAttribute("data-live", "true");
      expect(screen.getByTestId("status-ticker")).toHaveAttribute("data-live", "false");
    });
  });

  it("goes live when a later snapshot adds the agent's instance", async () => {
    const { instances, client } = livenessFake();
    renderRegistry(client);
    await screen.findByText("ticker");

    instances.push({ "host-1": ["translator"] });
    await waitFor(() => expect(screen.getByTestId("status-ticker")).toHaveAttribute("data-live", "false"));

    instances.push({ "host-1": ["translator"], "host-2": ["ticker"] });
    await waitFor(() => expect(screen.getByTestId("status-ticker")).toHaveAttribute("data-live", "true"));
  });

  it("flips an agent to offline the moment its death notice arrives", async () => {
    const { instances, deaths, client } = livenessFake();
    renderRegistry(client);
    await screen.findByText("translator");

    instances.push({ "host-1": ["translator", "ticker"] });
    await waitFor(() => expect(screen.getByTestId("status-translator")).toHaveAttribute("data-live", "true"));

    deaths.push({ subject: "mesh.death.translator", payload: { instance_id: "host-1" }, isError: false });
    await waitFor(() => expect(screen.getByTestId("status-translator")).toHaveAttribute("data-live", "false"));
    // The other agent served by the same host stays live until KV catches up.
    expect(screen.getByTestId("status-ticker")).toHaveAttribute("data-live", "true");
  });
});
