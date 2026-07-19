import { NotFound } from "@openagentmesh/sdk";
import type { AgentContract, CatalogEntry } from "@openagentmesh/sdk";
import type { MeshClient } from "../src/mesh";

export const TRANSLATOR: AgentContract = {
  name: "translator",
  description: "Translate text between languages. Uses an LLM under the hood.",
  version: "1.2.0",
  capabilities: { invocable: true, streaming: false },
  skills: [
    {
      id: "translator",
      inputSchema: {
        type: "object",
        properties: { text: { type: "string" }, target_lang: { type: "string" } },
        required: ["text", "target_lang"],
      },
      outputSchema: {
        type: "object",
        properties: { translated: { type: "string" } },
      },
    },
  ],
  subject: "mesh.agent.translator",
  tags: ["nlp", "demo"],
  invocable: true,
  streaming: false,
  inputSchema: {
    type: "object",
    properties: { text: { type: "string" }, target_lang: { type: "string" } },
    required: ["text", "target_lang"],
  },
  outputSchema: {
    type: "object",
    properties: { translated: { type: "string" } },
  },
  registeredAt: "2026-07-19T08:00:00Z",
};

export const TICKER: AgentContract = {
  name: "ticker",
  description: "Stream market ticks for a symbol.",
  version: "0.3.1",
  capabilities: { invocable: true, streaming: true },
  skills: [{ id: "ticker" }],
  subject: "mesh.agent.ticker",
  tags: ["finance"],
  invocable: true,
  streaming: true,
  chunkSchema: { type: "object", properties: { price: { type: "number" } } },
};

function toCatalogEntry(c: AgentContract): CatalogEntry {
  return {
    name: c.name,
    description: c.description,
    version: c.version,
    tags: c.tags,
    invocable: c.invocable,
    streaming: c.streaming,
  };
}

/** In-memory MeshClient backed by a fixed contract list. */
export function fakeMesh(contracts: AgentContract[] = [TRANSLATOR, TICKER]): MeshClient {
  return {
    catalog: async () => contracts.map(toCatalogEntry),
    contract: async (name: string) => {
      const found = contracts.find((c) => c.name === name);
      if (!found) throw new NotFound(`Agent '${name}' not found`, { agent: name });
      return found;
    },
    close: async () => {},
  };
}
