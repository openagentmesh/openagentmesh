import { Kvm } from "@nats-io/kv";
import { jetstream } from "@nats-io/jetstream";
import { ensureConnection } from "./nats";

// Full agent contract from the "mesh-registry" KV bucket (key = agent name).
// Wire shape is AgentContract.to_registry_json(): A2A Agent Card superset
// with OAM extras under "x-agentmesh". Input/output JSON Schemas ride on
// skills[0].inputSchema / .outputSchema.
export type JsonSchema = {
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  enum?: unknown[];
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  default?: unknown;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  $defs?: Record<string, JsonSchema>;
  $ref?: string;
  [k: string]: unknown;
};

export type AgentRegistryDoc = {
  name: string;
  description: string;
  version: string;
  capabilities: { streaming: boolean; invocable: boolean };
  skills: Array<{
    id: string;
    name: string;
    description: string;
    tags: string[];
    inputSchema?: JsonSchema;
    outputSchema?: JsonSchema;
  }>;
  "x-agentmesh": {
    subject: string;
    tags: string[];
    registered_at: string;
    chunk_schema?: JsonSchema;
  };
};

export function inputSchemaOf(doc: AgentRegistryDoc): JsonSchema | undefined {
  return doc.skills?.[0]?.inputSchema;
}

export function outputSchemaOf(doc: AgentRegistryDoc): JsonSchema | undefined {
  return doc.skills?.[0]?.outputSchema;
}

// Watch every key in mesh-registry and mirror into a name → doc map.
export async function watchRegistry(
  onUpdate: (docs: Record<string, AgentRegistryDoc>) => void,
): Promise<() => void> {
  const nc = await ensureConnection();
  const js = jetstream(nc);
  const kv = await new Kvm(js).open("mesh-registry");
  const watcher = await kv.watch();
  const decoder = new TextDecoder();
  const docs: Record<string, AgentRegistryDoc> = {};
  let cancelled = false;
  (async () => {
    for await (const e of watcher) {
      if (cancelled) break;
      const op = (e as { operation?: string }).operation;
      if (op === "DEL" || op === "DELETE" || op === "PURGE" || !e.value?.length) {
        delete docs[e.key];
        onUpdate({ ...docs });
        continue;
      }
      try {
        docs[e.key] = JSON.parse(decoder.decode(e.value)) as AgentRegistryDoc;
        onUpdate({ ...docs });
      } catch {
        // malformed registry payloads are skipped, not fatal
      }
    }
  })();
  return () => {
    cancelled = true;
    watcher.stop();
  };
}

// Resolve a JSON Schema $ref against the schema's own $defs (Pydantic emits
// "#/$defs/Name" refs for nested models). Non-local refs return undefined.
export function resolveRef(
  root: JsonSchema,
  schema: JsonSchema | undefined,
): JsonSchema | undefined {
  if (!schema) return undefined;
  if (!schema.$ref) return schema;
  const m = /^#\/\$defs\/(.+)$/.exec(schema.$ref);
  if (!m) return undefined;
  return root.$defs?.[m[1]];
}
