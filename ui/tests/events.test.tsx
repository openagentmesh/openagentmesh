import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { TapEvent } from "@openagentmesh/sdk";
import App from "../src/App";
import { MeshProvider } from "../src/MeshProvider";
import type { MeshClient } from "../src/mesh";
import { fakeMesh, pushableQueue } from "./fakes";

function renderEvents(client: MeshClient) {
  render(
    <MemoryRouter initialEntries={["/events"]}>
      <MeshProvider client={client}>
        <App />
      </MeshProvider>
    </MemoryRouter>,
  );
}

function feedFake() {
  const feed = pushableQueue<TapEvent>();
  const tapped: string[] = [];
  const client = fakeMesh(undefined, {
    tap: (subject, opts) => {
      tapped.push(subject);
      return feed.iterate(opts?.signal);
    },
  });
  return { feed, tapped, client };
}

describe("event feed screen", () => {
  it("shows a pattern input pre-filled with mesh.> and a Subscribe button", async () => {
    renderEvents(fakeMesh());
    expect(await screen.findByRole("textbox", { name: /pattern/i })).toHaveValue("mesh.>");
    expect(screen.getByRole("button", { name: /subscribe/i })).toBeInTheDocument();
  });

  it("renders tapped events with subject and payload after subscribing", async () => {
    const { feed, tapped, client } = feedFake();
    renderEvents(client);
    await userEvent.click(await screen.findByRole("button", { name: /subscribe/i }));
    expect(tapped).toEqual(["mesh.>"]);

    feed.push({ subject: "mesh.logs.translator", payload: { event: "request_completed", ms: 12 }, isError: false });
    expect(await screen.findByText("mesh.logs.translator")).toBeInTheDocument();
    expect(screen.getByText(/request_completed/)).toBeInTheDocument();
  });

  it("subscribes to the pattern the user typed", async () => {
    const { tapped, client } = feedFake();
    renderEvents(client);
    const input = await screen.findByRole("textbox", { name: /pattern/i });
    await userEvent.clear(input);
    await userEvent.type(input, "mesh.death.>");
    await userEvent.click(screen.getByRole("button", { name: /subscribe/i }));
    expect(tapped).toEqual(["mesh.death.>"]);
  });

  it("marks error-envelope events", async () => {
    const { feed, client } = feedFake();
    renderEvents(client);
    await userEvent.click(await screen.findByRole("button", { name: /subscribe/i }));

    feed.push({ subject: "mesh.errors.ticker", payload: { code: "handler_error", message: "boom" }, isError: true });
    const row = (await screen.findByText("mesh.errors.ticker")).closest("li");
    expect(row).not.toBeNull();
    expect(row!).toHaveTextContent("error");
  });

  it("pause buffers incoming events and resume flushes them", async () => {
    const { feed, client } = feedFake();
    renderEvents(client);
    await userEvent.click(await screen.findByRole("button", { name: /subscribe/i }));

    feed.push({ subject: "mesh.logs.a", payload: { n: 1 }, isError: false });
    await screen.findByText("mesh.logs.a");

    await userEvent.click(screen.getByRole("button", { name: /pause/i }));
    feed.push({ subject: "mesh.logs.b", payload: { n: 2 }, isError: false });
    // A paused feed must not render the new event.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText("mesh.logs.b")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /resume/i }));
    expect(await screen.findByText("mesh.logs.b")).toBeInTheDocument();
  });

  it("clear empties the feed", async () => {
    const { feed, client } = feedFake();
    renderEvents(client);
    await userEvent.click(await screen.findByRole("button", { name: /subscribe/i }));

    feed.push({ subject: "mesh.logs.a", payload: { n: 1 }, isError: false });
    await screen.findByText("mesh.logs.a");

    await userEvent.click(screen.getByRole("button", { name: /clear/i }));
    expect(screen.queryByText("mesh.logs.a")).not.toBeInTheDocument();
  });

  it("unsubscribe stops the feed and restores the Subscribe button", async () => {
    const { feed, client } = feedFake();
    renderEvents(client);
    await userEvent.click(await screen.findByRole("button", { name: /subscribe/i }));
    await userEvent.click(screen.getByRole("button", { name: /unsubscribe/i }));
    expect(await screen.findByRole("button", { name: /^subscribe/i })).toBeInTheDocument();

    feed.push({ subject: "mesh.logs.late", payload: { n: 9 }, isError: false });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText("mesh.logs.late")).not.toBeInTheDocument();
  });
});
