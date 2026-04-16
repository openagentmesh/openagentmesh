# AgentMesh — Registry, Discovery, and Navigation

**Status:** Working design document  
**Last updated:** April 2026

---

## 1. Overview

The registry is the backbone of agent discovery on the mesh. It stores agent contracts in a NATS JetStream KV bucket and exposes them through a structured namespace that supports both programmatic enumeration and LLM-driven tool selection.

This document covers:

- Channel-based namespace hierarchy
- The two-tier data model (catalog vs. full contract)
- Discovery patterns at different scales
- LLM-compatible tool selection without external infrastructure

---

## 2. Channels: Hierarchical Agent Namespaces

### 2.1 The Problem with Flat Namespaces

The original spec uses a flat subject convention:

```
mesh.agent.summarizer
mesh.agent.classifier
mesh.agent.pdf-extractor
```

This is manageable at 10–20 agents. At 100+, it becomes an undifferentiated list with no organizational structure. Developers cannot scope discovery to a relevant subset, and LLMs cannot efficiently select from hundreds of unstructured options.

### 2.2 Channel Convention

Agents register under a channel — a dot-separated namespace prefix that groups related capabilities:

```
mesh.agent.nlp.summarizer
mesh.agent.nlp.classifier
mesh.agent.nlp.translator
mesh.agent.documents.pdf-extractor
mesh.agent.documents.ocr
mesh.agent.finance.invoice-parser
mesh.agent.finance.risk.fraud-detector
mesh.agent.finance.risk.credit-scorer
```

Channels map directly to NATS subject hierarchy, which enables wildcard subscriptions:

- `mesh.agent.nlp.*` — all NLP agents
- `mesh.agent.finance.>` — all finance agents, including nested channels like `finance.risk`
- `mesh.agent.>` — every agent on the mesh

**SDK filtering vs. NATS wildcards:** `mesh.catalog(channel="nlp")` is SDK-level filtering: it reads the single `mesh-catalog` KV key and filters entries client-side by channel prefix. NATS subject wildcards (`*` for single token, `>` for any depth) are a separate, protocol-level mechanism that operates on subject subscriptions (e.g., `mesh.agent.nlp.*`). The SDK does not expose NATS wildcards as an API; they are available to developers who subscribe to NATS subjects directly. See ADR-0020.

### 2.3 Registration with Channels

```python
@mesh.agent(
    name="summarizer",
    channel="nlp",
    description="Summarizes text to a target length.",
)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...
```

The full NATS subject becomes `mesh.agent.nlp.summarizer`. The registry key becomes `mesh.registry.nlp.summarizer`.

Channels can be nested for large organizations:

```python
@mesh.agent(
    name="fraud-detector",
    channel="finance.risk",
    description="Detects fraudulent transaction patterns.",
)
```

If no channel is specified, the agent registers at the root: `mesh.agent.{name}`. This is fine for small meshes and local development.

### 2.4 Channel Design Guidance

Channels are organizational, not functional. They represent **domains or teams**, not technical categories. This mirrors how enterprises organize services in a service mesh.

Good channel structures:

```
nlp/                    # natural language processing team
documents/              # document processing pipeline
finance/                # finance department
  finance.risk/         # risk analysis sub-team
  finance.reporting/    # financial reporting
customer/               # customer-facing services
internal/               # internal tooling
```

Anti-patterns to avoid:

```
llm-agents/             # implementation detail, not a domain
fast/                   # performance tier, not organizational
v2/                     # version, not a channel (use contract versioning)
```

---

## 3. Two-Tier Data Model: Catalog vs. Contract

### 3.1 The Problem

A full agent contract includes JSON Schemas for input and output models, SLA metadata, versioning information, and implementation details. A single contract might be 2–5 KB of JSON. At 200 agents, pulling all full contracts means nearly 1 MB of schema data — far too much to inject into an LLM context for tool selection.

But the information needed to *decide* which agent to call is much smaller: just the name, channel, description, and version. That's 20–30 tokens per agent.

### 3.2 The Catalog

The catalog is a lightweight index of all registered agents. It contains just enough information for scanning, filtering, and LLM-based selection.

**Catalog entry structure:**

```json
{
  "name": "summarizer",
  "channel": "nlp",
  "description": "Summarizes input text to a target length. Handles documents, articles, and raw text. Not suitable for code or structured data.",
  "version": "1.0.0",
  "type": "agent",
  "tags": ["text", "summarization", "nlp"]
}
```

**Storage:** The catalog is stored as a single JSON array in a dedicated KV key: `mesh.catalog`. It is updated on every agent registration and deregistration. This is a denormalized index — a tradeoff of slight staleness for read performance (one KV read instead of enumerating all registry keys).

**Staleness window:** Since registration and deregistration are infrequent (process startup/shutdown, not per-request), the catalog is effectively consistent with the full registry under normal operation.

### 3.3 The Full Contract

The full contract is stored per-agent in the registry KV bucket at `mesh.registry.{channel}.{name}`. It includes everything in the catalog entry plus:

- `input_schema` — full JSON Schema for the agent's input model
- `output_schema` — full JSON Schema for the agent's output model
- `error_schema` — JSON Schema for the agent's error responses
- `sla` — expected latency, timeout, retry policy
- `metadata` — framework, language, registration timestamp, heartbeat interval

The full contract is structured as a superset of the A2A Agent Card format. A2A-defined fields appear at the top level; AgentMesh-specific fields are namespaced under `x-agentmesh`. This means any AgentMesh contract is a valid A2A Agent Card when a `url` is injected at the federation boundary — no structural transformation required.

Full contract structure:

```json
{
  "name": "summarizer",
  "description": "Summarizes input text to a target length. Handles documents, articles, and raw text. Not suitable for code or structured data.",
  "version": "1.0.0",
  "capabilities": {
    "streaming": false,
    "pushNotifications": true
  },
  "defaultInputModes": ["application/json"],
  "defaultOutputModes": ["application/json"],
  "skills": [
    {
      "id": "summarizer",
      "name": "Summarize text",
      "description": "Summarizes input text to a target length. Handles documents, articles, and raw text. Not suitable for code or structured data.",
      "tags": ["text", "summarization", "nlp"],
      "inputModes": ["application/json"],
      "outputModes": ["application/json"],
      "inputSchema": {
        "type": "object",
        "properties": {
          "text": { "type": "string", "description": "The text to summarize" },
          "max_length": { "type": "integer", "default": 200, "description": "Target summary length in words" }
        },
        "required": ["text"]
      },
      "outputSchema": {
        "type": "object",
        "properties": {
          "summary": { "type": "string" },
          "token_count": { "type": "integer" }
        },
        "required": ["summary", "token_count"]
      }
    }
  ],
  "x-agentmesh": {
    "type": "agent",
    "channel": "nlp",
    "subject": "mesh.agent.nlp.summarizer",
    "sla": {
      "expected_latency_ms": 5000,
      "timeout_ms": 30000,
      "retry_policy": "idempotent",
      "max_retries": 2
    },
    "error_schema": {
      "code": "string",
      "message": "string",
      "details": "object"
    },
    "metadata": {
      "framework": "custom",
      "language": "python",
      "registered_at": "2026-04-01T10:00:00Z",
      "heartbeat_interval_ms": 10000
    }
  }
}
```

---

## 4. SDK Discovery API

### 4.1 Method Summary

| Method | Returns | Use Case |
|---|---|---|
| `mesh.catalog()` | List of lightweight entries (name, channel, description, version, tags) | Scanning what's available; LLM tool selection; building UIs |
| `mesh.catalog(channel="nlp")` | Filtered catalog entries | Scoped scanning within a domain |
| `mesh.discover()` | List of full `AgentContract` objects | Getting complete schemas for tool injection |
| `mesh.discover(channel="nlp")` | Filtered full contracts | Scoped full discovery within a domain |
| `mesh.contract("summarizer")` | Single `AgentContract` object | Fetching one agent's full details after selection |

> **Intentionally omitted:** `mesh.tags()` and `mesh.channels()` are not provided as separate discovery methods. The catalog (~20-30 tokens/agent) fits in LLM context; tag and channel values are derivable client-side from catalog results without an extra round-trip. The catalog is the sole discovery primitive. See ADR-0009.

### 4.2 Catalog API

```python
# List everything on the mesh (lightweight)
catalog = await mesh.catalog()
# Returns: [
#   {"name": "summarizer", "channel": "nlp", "description": "...", "version": "1.0.0", "tags": [...]},
#   {"name": "classifier", "channel": "nlp", "description": "...", "version": "1.2.0", "tags": [...]},
#   {"name": "pdf-extractor", "channel": "documents", "description": "...", "version": "2.0.0", "tags": [...]},
#   ...
# ]

# Filter by channel
nlp_catalog = await mesh.catalog(channel="nlp")

# Filter by nested channel (includes children)
risk_catalog = await mesh.catalog(channel="finance.risk")

# Filter by tags
summarizers = await mesh.catalog(tags=["summarization"])
```

### 4.3 Full Discovery API

```python
# Full contracts for all agents
agents = await mesh.discover()
# Returns: list of AgentContract objects with full schemas

# Filtered by channel
nlp_agents = await mesh.discover(channel="nlp")

# Single agent's full contract
contract = await mesh.contract("summarizer")
# Returns: AgentContract with input_schema, output_schema, sla, etc.
```

### 4.4 The AgentContract Object

```python
contract = await mesh.contract("summarizer")

# A2A top-level fields
contract.name              # "summarizer"
contract.description       # "Summarizes input text to a target length..."
contract.version           # "1.0.0"
contract.capabilities      # {"streaming": False, "pushNotifications": True}
contract.skills            # list of skill dicts (A2A format)

# Convenience accessors (read from skills[0])
contract.input_schema      # dict (JSON Schema) — skills[0]["inputSchema"]
contract.output_schema     # dict (JSON Schema) — skills[0]["outputSchema"]
contract.tags              # list — skills[0]["tags"]

# AgentMesh extension fields (from x-agentmesh)
contract.channel           # "nlp"
contract.subject           # "mesh.agent.nlp.summarizer"
contract.sla               # SLA object with timeout, latency, retry info
contract.type              # "agent"

# Tool conversion methods
contract.to_openai_tool()        # OpenAI function calling format
contract.to_anthropic_tool()     # Anthropic tool use format
contract.to_generic_tool()       # Framework-agnostic JSON Schema
contract.to_agent_card(url=None) # A2A Agent Card — injects url if provided
```

---

## 5. Discovery Patterns by Scale

### 5.1 Small Mesh (5–20 agents)

At this scale, the full registry fits comfortably in an LLM context. The simplest pattern is to discover everything and inject all contracts as tools.

```python
agents = await mesh.discover()
tools = [a.to_anthropic_tool() for a in agents]

# Pass all tools to the LLM — 20 tools is well within context limits
response = await llm.run(user_message, tools=tools)
```

No filtering needed. No selection logic. This is the default path for local development and small teams.

### 5.2 Medium Mesh (20–100 agents)

Channels become the primary filtering mechanism. The developer or their agent's system prompt specifies which channels are relevant.

```python
# Agent that works in the document processing domain
nlp_agents = await mesh.discover(channel="nlp")
doc_agents = await mesh.discover(channel="documents")
tools = [a.to_anthropic_tool() for a in nlp_agents + doc_agents]

# 15–25 tools from two channels — still manageable
response = await llm.run(user_message, tools=tools)
```

### 5.3 Large Mesh (100–500+ agents)

At this scale, even channel-filtered discovery may return too many agents. The recommended pattern is a **two-step approach**: catalog scan followed by targeted contract fetch.

**Step 1 — Catalog scan with LLM selection:**

```python
# Pull the lightweight catalog, optionally filtered by channel
catalog = await mesh.catalog(channel="documents")

# Feed catalog entries to the LLM as a selection task.
# Each entry is ~20-30 tokens. Even 500 entries is ~15,000 tokens.
selected_names = await my_llm.select_tools(
    task="Extract line items from this invoice PDF",
    available_agents=catalog,
    max_selections=5,
)
# LLM returns: ["pdf-extractor", "invoice-parser", "ocr"]
```

**Step 2 — Targeted contract fetch:**

```python
# Pull full contracts ONLY for the selected agents
tools = []
for name in selected_names:
    contract = await mesh.contract(name)
    tools.append(contract.to_anthropic_tool())

# Now invoke the LLM with just 3-5 highly relevant tools
response = await llm.run(user_message, tools=tools)
```

This pattern requires no additional infrastructure — no vector database, no embeddings, no RAG pipeline. It leverages the LLM's ability to scan short descriptions and select relevant capabilities from a manageable list.

### 5.4 Enterprise Scale (500+ agents)

At this scale, organizations will likely need infrastructure beyond what the SDK provides. The SDK's role is to expose registry data cleanly so that custom retrieval layers can be built on top.

Possible approaches (not part of the core SDK):

- **Embedding-based retrieval:** Index agent descriptions in a vector database (Chroma, Qdrant, pgvector). Perform semantic search to narrow candidates before LLM selection.
- **Service catalog integration:** Sync the mesh registry with existing service catalogs (Backstage, Cortex, internal portals).
- **Custom routing agents:** Build a dedicated routing agent that lives on the mesh, maintains its own index, and responds to "which agent should I use for X?" queries.

The SDK provides the raw data access. What organizations build on top is their concern:

```python
# Example: Custom discovery layer with embeddings (NOT part of SDK)
import chromadb

catalog = await mesh.catalog()
collection = chroma.create_collection("agent-registry")

for agent in catalog:
    collection.add(
        documents=[agent["description"]],
        ids=[agent["name"]],
        metadatas=[{"channel": agent["channel"], "tags": agent.get("tags", [])}],
    )

# Semantic search
results = collection.query(
    query_texts=["I need to process PDF invoices"],
    n_results=5,
)
```

---

## 6. Registry Storage Design

### 6.1 KV Layout

```
mesh.catalog                           → JSON array of lightweight entries
mesh.registry.nlp.summarizer           → full contract JSON
mesh.registry.nlp.classifier           → full contract JSON  
mesh.registry.documents.pdf-extractor  → full contract JSON
mesh.registry.finance.risk.fraud-detector → full contract JSON
```

### 6.2 Catalog Update Protocol

The catalog is updated atomically on every registration and deregistration event:

**On agent registration:**

1. Agent writes its full contract to `mesh.registry.{channel}.{name}`.
2. Agent reads the current catalog from `mesh.catalog`.
3. Agent appends its lightweight entry (or updates if already present).
4. Agent writes the updated catalog back to `mesh.catalog` using KV revision-based CAS (compare-and-swap) to prevent lost updates from concurrent registrations.
5. If CAS fails (another agent registered simultaneously), retry from step 2.

**On agent deregistration:**

1. Agent deletes its full contract from `mesh.registry.{channel}.{name}`.
2. Agent reads, removes its entry from, and writes the updated catalog using the same CAS pattern.

### 6.3 Consistency Guarantees

The CAS-based update ensures that concurrent registrations do not overwrite each other. In the worst case (high registration churn), retries add a few milliseconds of latency to the registration path — which is negligible since registration happens once per agent process lifecycle, not per request.

The catalog may be momentarily inconsistent with individual contracts during a registration in progress (contract written but catalog not yet updated). This window is milliseconds long and only affects discovery, not invocation. An agent that appears in the catalog but whose contract is not yet written will fail on `mesh.contract()` — the caller should handle this gracefully.

### 6.4 Tags

Tags are lightweight, unstructured string labels attached to agent contracts. They provide an additional filtering dimension beyond channels.

```python
@mesh.agent(
    name="summarizer",
    channel="nlp",
    description="Summarizes text to a target length.",
    tags=["text", "summarization", "content-processing"],
)
```

Tags are included in the catalog and can be used for filtering:

```python
catalog = await mesh.catalog(tags=["summarization"])
catalog = await mesh.catalog(channel="nlp", tags=["text"])
```

**Design guidance:** Channels represent organizational structure (teams, domains). Tags represent capabilities and use cases. An agent belongs to one channel but can have many tags.

---

## 7. Tool Conversion for LLM Providers

The `AgentContract` object includes convenience methods for converting the contract into provider-specific tool definitions. This is the bridge between "service mesh discovery" and "LLM tool use."

### 7.1 Anthropic Tool Format

```python
contract = await mesh.contract("summarizer")
tool = contract.to_anthropic_tool()

# Produces:
# {
#   "name": "summarizer",
#   "description": "Summarizes input text to a target length. Handles documents, articles, and raw text.",
#   "input_schema": {
#     "type": "object",
#     "properties": {
#       "text": {"type": "string", "description": "The text to summarize"},
#       "max_length": {"type": "integer", "default": 200}
#     },
#     "required": ["text"]
#   }
# }
```

### 7.2 OpenAI Tool Format

```python
tool = contract.to_openai_tool()

# Produces:
# {
#   "type": "function",
#   "function": {
#     "name": "summarizer",
#     "description": "Summarizes input text to a target length...",
#     "parameters": { ... }  # JSON Schema from input_model
#   }
# }
```

### 7.3 Generic Format

```python
tool = contract.to_generic_tool()

# Produces:
# {
#   "name": "summarizer",
#   "description": "...",
#   "input_schema": { ... },
#   "output_schema": { ... }
# }
```

### 7.4 A2A Agent Card Format

The AgentMesh contract schema is a superset of the A2A Agent Card format. All A2A-defined fields (`name`, `description`, `version`, `capabilities`, `defaultInputModes`, `defaultOutputModes`, `skills`) are stored at the top level of every contract. AgentMesh-specific fields (`channel`, `subject`, `sla`, `error_schema`, `metadata`) live under `x-agentmesh`, which A2A explicitly permits as an extension namespace.

As a result, `.to_agent_card()` is a thin projection, not a structural conversion:

```python
# No gateway URL — returns the stored contract as-is (valid A2A card minus url)
card = contract.to_agent_card()

# With a gateway URL — produces a fully spec-compliant A2A Agent Card
card = contract.to_agent_card(url="https://gateway.company.com/agents/nlp/summarizer")

# Produces:
# {
#   "name": "summarizer",
#   "description": "Summarizes input text to a target length...",
#   "url": "https://gateway.company.com/agents/nlp/summarizer",
#   "version": "1.0.0",
#   "capabilities": { "streaming": false, "pushNotifications": true },
#   "defaultInputModes": ["application/json"],
#   "defaultOutputModes": ["application/json"],
#   "skills": [
#     {
#       "id": "summarizer",
#       "name": "Summarize text",
#       "description": "...",
#       "tags": ["text", "summarization", "nlp"],
#       "inputModes": ["application/json"],
#       "outputModes": ["application/json"],
#       "inputSchema": { ... },
#       "outputSchema": { ... }
#     }
#   ],
#   "x-agentmesh": {
#     "channel": "nlp",
#     "subject": "mesh.agent.nlp.summarizer",
#     ...
#   }
# }
```

The `url` field is the only thing that cannot be stored in the registry — it is context-dependent (which gateway, which external hostname). An agent can serve its card over HTTP for external discovery by reading its own registry entry and calling `.to_agent_card(url=gateway_url)`. No A2A infrastructure is required internally; compatibility is a property of the schema, not the transport.

### 7.5 Description Quality Matters

The `description` field in a contract is the single most important field for LLM-based tool selection. It is not documentation for humans — it is a prompt for LLMs. It should clearly state:

- **What the agent does** — the core capability.
- **What kinds of inputs it handles** — data types, formats, domains.
- **When it should NOT be invoked** — explicit exclusions reduce misrouting.

Good description:

> Summarizes input text to a target length. Handles documents, articles, and raw text. Not suitable for code, structured data, or tabular content. Input must be plain text, not HTML or markdown.

Bad description:

> A summarizer agent.

This guidance should be emphasized in the SDK documentation and enforced via linting or warnings if a description is too short or too vague.

---

## 8. Summary of Design Decisions

| Decision | Rationale |
|---|---|
| Channels as hierarchical namespaces | Leverages NATS wildcard subscriptions; provides organizational structure at scale |
| Catalog as a denormalized lightweight index | Avoids full-registry enumeration; keeps scanning cost to a single KV read |
| Two-step discovery (catalog scan → contract fetch) | Enables LLM-based tool selection without RAG infrastructure |
| Tags as supplementary metadata | Provides cross-channel filtering without overloading the channel hierarchy |
| No built-in RAG or embedding layer | Keeps the SDK lean and dependency-free; advanced retrieval is user-space infrastructure |
| CAS-based catalog updates | Prevents lost writes during concurrent registration without external coordination |
| Contract schema as A2A superset | A2A fields at top level, AgentMesh extensions under `x-agentmesh`; contracts are natively A2A-compatible — `.to_agent_card(url)` is a projection, not a conversion |
| Tool conversion methods on AgentContract | Bridges service mesh discovery with LLM tool use patterns; all provider formats derived from the same stored contract |
