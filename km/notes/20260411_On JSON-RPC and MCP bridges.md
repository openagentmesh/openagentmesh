  - Should we set JSON-RPC2.0 as a message standard? That would match MCP specification and could turn useful for error handling (even though we could use NATS headers).
    
    10:06
    
    Weighed JSON-RPC redundancy against NATS architecture benefits
    
    ## Don't adopt JSON-RPC 2.0 as the internal message standard. Here's the full reasoning.
    
    ### The core problem: JSON-RPC solves a problem NATS already solved
    
    JSON-RPC 2.0 was designed for **transport-agnostic RPC** where routing information must live *inside the message body* — because the transport (HTTP, stdio, WebSocket) is dumb. Its `method` field tells a generic endpoint what to do. Its `id` field correlates requests to responses when the transport has no session concept.
    
    NATS is not dumb. Every structural concern JSON-RPC addresses is already handled — better — at the NATS layer:
    
    | JSON-RPC 2.0 field | NATS equivalent                         | Notes                                     |
    | ------------------ | --------------------------------------- | ----------------------------------------- |
    | `method`           | Subject (`mesh.agent.nlp.summarizer`)   | Encoded in routing, zero payload overhead |
    | `id`               | `X-Mesh-Request-Id` header + NATS inbox | Built into req/reply semantics            |
    | `params`           | Raw JSON body                           | Pure payload, no wrapper                  |
    | `result`           | Raw JSON body on reply                  | Validated against `output_schema`         |
    | `error`            | `X-Mesh-Status: error` + error body     | More expressive than JSON-RPC error codes |
    | Notifications      | Pub/sub to `mesh.agent.{name}.events`   | First-class primitive, not a workaround   |
    
    Adding JSON-RPC on top of NATS means the `method` field is always redundant (the subject already routed the message), `id` is duplicated (you already have `X-Mesh-Request-Id`), and every message carries a JSON-RPC wrapper that adds zero information density.
    
    ------
    
    ### The pub/sub problem kills the argument
    
    JSON-RPC 2.0 is fundamentally a request/response protocol. Its handling of one-way messages ("notifications") is a bolt-on — you send a request with no `id`, the receiver is expected to not reply. There's no concept of fan-out, no concept of a message being consumed by zero-to-N subscribers independently, no streaming primitive.
    
    AgentMesh's pub/sub pattern — publisher agents emitting to `mesh.agent.{name}.events`, subscriber agents consuming independently — is architecturally incompatible with JSON-RPC's mental model. You'd be forcing an event-driven first-class primitive into a protocol that treats it as an afterthought.
    
    ------
    
    ### Your error handling is already better
    
    The JSON-RPC error object:
    
    json
    
    ```json
    {
      "jsonrpc": "2.0",
      "error": { "code": -32600, "message": "Invalid Request", "data": null },
      "id": null
    }
    ```
    
    The AgentMesh error envelope (from your spec):
    
    json
    
    ```json
    {
      "code": "validation_error | handler_error | timeout | not_found | rate_limited",
      "message": "Human-readable description",
      "agent": "summarizer",
      "request_id": "uuid",
      "details": {}
    }
    ```
    
    Yours is semantically richer, agent-aware, and correlated to a specific request. JSON-RPC's integer error codes (-32700, -32600, etc.) are designed for generic JSON-RPC infrastructure problems, not domain-specific agent failures. You'd either awkwardly map your error taxonomy onto JSON-RPC codes or carry a custom `data` field that duplicates your envelope anyway.
    
    And critically: `X-Mesh-Status: error` in the NATS header means a consumer can branch on success vs. error *before parsing the body* — zero-copy error routing. JSON-RPC requires deserializing the full envelope to distinguish a result from an error.
    
    ------
    
    ### The MCP compatibility argument doesn't hold
    
    MCP uses JSON-RPC 2.0, but MCP runs over stdio or HTTP — it's a point-to-point tool-calling protocol. AgentMesh is an event-driven mesh. These aren't in the same layer. The MCP familiarity argument is "JSON-RPC is familiar to developers who've read the MCP spec," which is a thin reason to adopt significant architectural overhead.
    
    The A2A protocol uses JSON-RPC 2.0 over HTTP at the *federation boundary*. This is relevant: when you expose an AgentMesh agent externally via an A2A gateway, that HTTP boundary should speak JSON-RPC 2.0 — because A2A says so. But that's a *translation at the perimeter*, not the internal wire format. Internally, the mesh stays clean.
    
    ------
    
    ### The right boundary for JSON-RPC
    
    ```
    Internal (AgentMesh)              External boundary
    ─────────────────────────────────────────────────────
    NATS subjects                     HTTP endpoints
    NATS headers (metadata)           JSON-RPC 2.0 envelope  ← A2A/MCP compatible
    Raw JSON bodies (payloads)        JSON-RPC params/result
    AgentMesh error envelope          JSON-RPC error object
    ```
    
    The A2A gateway (your Phase 4 deliverable) is where JSON-RPC lives. It receives an A2A-formatted JSON-RPC call over HTTP, translates it into a NATS pub to `mesh.agent.{channel}.{name}`, awaits the reply, and wraps the response back in a JSON-RPC envelope. That gateway is a thin adapter — maybe 100 lines — and it keeps the internal mesh clean.
    
    ------
    
    ### Verdict
    
    Keep your current envelope design. It's the right call architecturally:
    
    - NATS subjects handle routing (replacing `method`)
    - NATS headers handle metadata (replacing `id`, status)
    - Raw JSON bodies stay clean and typed against Pydantic schemas
    - Your error envelope is richer and more agent-aware than JSON-RPC codes
    - Pub/sub remains a first-class pattern, not a hack
    
    Adopt JSON-RPC 2.0 only at the A2A gateway boundary in Phase 4 — where HTTP is the transport and the spec mandates it. That's the architecturally honest place for it.
    
    and also if we get to doing MCP adapters, something like `mesh.run_mcp()` or if we want to connect external MCPs to the mesh and have mesh agents call them seamlessly, e.g. `mesh.add_mcp()`)
    
    10:27
    
    Architected bidirectional MCP integration patterns for mesh agents
    
    Both directions are worth designing carefully because they're architecturally different problems with different failure modes. Let me work through each.
    
    ------
    
    ## The two directions are not symmetric
    
    ```
    MCP Client                    AgentMesh Mesh                    MCP Server
    (Claude Desktop,    ←→    [NATS fabric + agents]    ←→    (filesystem, GitHub,
     Cursor, etc.)                                               Brave search, etc.)
    
         mesh.run_mcp()                                    mesh.add_mcp()
      "expose outward"                                   "consume inward"
    ```
    
    `run_mcp()` makes the mesh look like an MCP server to the outside world. `add_mcp()` makes external MCP servers look like mesh agents to the inside world. The translation direction and the trust/lifecycle concerns flip completely.
    
    ------
    
    ## Direction 1: `mesh.run_mcp()` — Exposing agents as MCP tools
    
    ### What it does
    
    Starts an MCP server (stdio or HTTP/SSE) that proxies calls to the mesh. An MCP client calls `tools/list`, gets all mesh agents as tools. Calls `tools/call`, the bridge forwards via `mesh.call()`, returns the result.
    
    The contract-to-MCP-tool conversion is trivial because your `AgentContract` already holds JSON Schema. MCP's tool format is essentially identical to what `.to_anthropic_tool()` produces.
    
    ### API design
    
    python
    
    ```python
    # Expose all agents on the mesh as MCP tools
    mesh.run_mcp()  # stdio transport (default — Claude Desktop, Cursor compatible)
    
    # HTTP/SSE transport for remote MCP clients
    mesh.run_mcp(transport="http", port=8080)
    
    # Scoped exposure — only expose certain channels
    mesh.run_mcp(channel="nlp")
    mesh.run_mcp(channel=["nlp", "documents"])
    
    # Explicit allowlist — only expose agents you deliberately publish
    mesh.run_mcp(allow=["summarizer", "classifier"])
    
    # Composable: run both the mesh event loop AND the MCP server
    await mesh.start()
    await mesh.start_mcp(transport="http", port=8080)
    ```
    
    ### The key design decision: opt-in vs opt-out exposure
    
    Should `mesh.run_mcp()` with no filters expose everything? I'd say **no, opt-in by default for production, opt-out for local dev**.
    
    Reason: in a composable mesh, internal implementation agents (a `chunk-router` that only makes sense inside a pipeline, a `cost-tracker` that's an internal control plane agent) should not automatically surface to external MCP clients. A Claude Desktop user calling `tools/list` and getting 80 agents, half of which are internal plumbing, is a bad experience.
    
    python
    
    ```python
    # Registration-side: mark agents as MCP-exportable
    @mesh.agent(
        name="summarizer",
        channel="nlp",
        description="...",
        export=["mcp"],  # or export=True for all external protocols
    )
    async def summarize(req: SummarizeInput) -> SummarizeOutput:
        ...
    
    # For local dev, run_mcp() with no filters exposes everything
    # (enclosed mode assumption: you own all the agents)
    mesh = AgentMesh.local()
    mesh.run_mcp()  # fine, everything is yours
    ```
    
    ### Schema translation
    
    python
    
    ```python
    # This is the entire MCP tool definition logic — it's that thin
    def to_mcp_tool(contract: AgentContract) -> dict:
        return {
            "name": contract.name,
            "description": contract.description,
            "inputSchema": contract.input_schema,  # already JSON Schema
        }
    ```
    
    MCP doesn't define an output schema — the result is untyped text/content from the MCP server's perspective. Your agents' `output_schema` becomes documentation in the description, not a structural constraint on the MCP side.
    
    ### Failure mode to anticipate
    
    MCP clients expect tool calls to return quickly (it's a synchronous JSON-RPC call). Mesh agents can have wildly different SLA profiles — a human-in-the-loop agent might take 30 minutes. The MCP bridge should read the `sla.timeout_ms` from the contract and surface it somehow, or at minimum refuse to expose agents whose timeout exceeds a configurable MCP-bridge maximum.
    
    ------
    
    ## Direction 2: `mesh.add_mcp()` — Consuming external MCP servers
    
    ### What it does
    
    Connects to an external MCP server, enumerates its tools via `tools/list`, derives AgentMesh contracts from their schemas, registers them as **virtual agents** in the mesh catalog. When any mesh agent calls one via `mesh.call("github.create-issue", ...)`, the bridge translates the call into a JSON-RPC `tools/call`, gets the result, and returns it as a normal mesh response.
    
    From the perspective of any mesh agent, MCP tools are just agents. They appear in `mesh.catalog()`, they have contracts, they're callable via `mesh.call()`. The NATS transport boundary is transparent.
    
    ### API design
    
    python
    
    ```python
    # stdio MCP server (most common for local tools)
    await mesh.add_mcp(
        "uvx mcp-server-filesystem",
        channel="tools.filesystem",  # where it appears in the mesh
    )
    
    # HTTP/SSE MCP server
    await mesh.add_mcp(
        "https://mcp.github.com/sse",
        channel="tools.github",
        auth={"token": os.environ["GITHUB_TOKEN"]},
    )
    
    # With an explicit command list (safer than shell string)
    await mesh.add_mcp(
        ["npx", "-y", "@modelcontextprotocol/server-brave-search"],
        channel="tools.search",
        env={"BRAVE_API_KEY": os.environ["BRAVE_API_KEY"]},
    )
    ```
    
    ### The lifecycle problem — this is the hard part
    
    MCP servers are **session-oriented**. A stdio MCP server is a subprocess with a persistent connection; an HTTP/SSE server maintains a session. This is fundamentally different from a stateless mesh agent that subscribes to a NATS subject and handles independent requests.
    
    The bridge must manage this:
    
    ```
    mesh.add_mcp() creates an MCP Bridge process:
      ├── Spawns/connects the MCP server
      ├── Calls initialize + tools/list
      ├── Registers virtual agents in mesh catalog (type: "mcp_bridge")
      ├── Subscribes to NATS subjects for each tool
      │     mesh.agent.tools.github.create-issue
      │     mesh.agent.tools.github.list-repos
      │     ...
      ├── Maintains the MCP session (reconnect on failure)
      └── On shutdown: deregisters all virtual agents, closes MCP session
    ```
    
    The bridge is essentially a long-lived NATS subscriber that proxies to the MCP server. If the MCP server crashes, the bridge detects it, removes the virtual agents from the catalog, and optionally tries to reconnect.
    
    python
    
    ```python
    await mesh.add_mcp(
        "https://mcp.github.com/sse",
        channel="tools.github",
        reconnect=True,           # auto-reconnect on MCP server failure
        reconnect_backoff="exponential",
    )
    ```
    
    ### Contract derivation
    
    MCP tool schemas are JSON Schema. Deriving a mesh contract is clean:
    
    python
    
    ```python
    def mcp_tool_to_contract(tool: dict, channel: str, bridge_id: str) -> AgentContract:
        return AgentContract(
            name=tool["name"],
            channel=channel,
            description=tool.get("description", ""),
            version="1.0.0",
            input_schema=tool["inputSchema"],
            output_schema={"type": "object"},  # MCP results are untyped
            type="mcp_bridge",                 # distinguishable from native agents
            x_agentmesh={
                "bridge": bridge_id,
                "source": "mcp",
            }
        )
    ```
    
    The `output_schema` being untyped is a real limitation — MCP doesn't define output schemas. In practice, mesh agents calling an MCP bridge tool will get back whatever the MCP server returns (text, structured content, etc.), without Pydantic validation on the output. This should be documented clearly.
    
    ### Discoverability
    
    Virtual agents from MCP bridges appear in `mesh.catalog()` naturally:
    
    python
    
    ```python
    catalog = await mesh.catalog()
    # Returns:
    # [
    #   {"name": "summarizer",     "channel": "nlp",              "type": "agent",      ...},
    #   {"name": "classifier",     "channel": "nlp",              "type": "agent",      ...},
    #   {"name": "create-issue",   "channel": "tools.github",     "type": "mcp_bridge", ...},
    #   {"name": "list-repos",     "channel": "tools.github",     "type": "mcp_bridge", ...},
    #   {"name": "brave-search",   "channel": "tools.search",     "type": "mcp_bridge", ...},
    # ]
    
    # Filter to only native agents
    catalog = await mesh.catalog(type="agent")
    
    # Filter to only MCP-bridged tools
    catalog = await mesh.catalog(type="mcp_bridge")
    ```
    
    ------
    
    ## The full picture
    
    ```
    ┌─────────────────────────────────────────────────────────────────┐
    │                        AgentMesh Fabric                         │
    │                                                                 │
    │  ┌──────────┐    ┌──────────┐    ┌──────────────────────────┐  │
    │  │summarizer│    │classifier│    │  MCP Bridge              │  │
    │  │(native)  │    │(native)  │    │  tools.github.*          │  │
    │  └────┬─────┘    └────┬─────┘    │  tools.filesystem.*      │  │
    │       │               │          └──────────┬───────────────┘  │
    │       └───────────────┴──────── NATS ────────┘                 │
    │                                     │                           │
    └─────────────────────────────────────┼───────────────────────────┘
                                          │
                  ┌───────────────────────┼────────────────────┐
                  │                       │                    │
                  ▼                       ▼                    ▼
           MCP Client              GitHub MCP Server    Filesystem MCP
        (mesh.run_mcp())           (mesh.add_mcp())     (mesh.add_mcp())
        Claude Desktop
        Cursor
    ```
    
    ------
    
    ## What to add to the spec / ideas doc
    
    A few things worth capturing before you forget them:
    
    **MCP tool output schema gap.** MCP tools don't declare output schemas. Mesh agents calling MCP bridge tools can't get Pydantic-validated outputs. The bridge should optionally accept a `output_model` override so the developer can add validation on the mesh side.
    
    **Resource and prompt support.** MCP servers expose not just tools but resources (file contents, URIs) and prompts (templated messages). Both are out of scope for the bridge initially, but resources map naturally to `mesh.workspace` (Object Store) and prompts could eventually map to a `mesh.prompts.*` namespace.
    
    **Phase placement.** `run_mcp()` is Phase 2 — it's the discovery-to-tool-injection story made concrete for the most popular external client ecosystem. `add_mcp()` is Phase 3 — it requires the bridge process lifecycle management, which is adjacent to the spawner work anyway.
    
    A few things: 
    
    1) external MCP tool may not have a compliant input and output schema. We need to take this into account
    2) as for sla level and outgoing MCP mode, I guess we could flag internal agents/tools on the mesh as “MCP-able” or not.
    3) MCPs stream responses, are we accounting for that?
    
    11:00
    
    Architected schema validation, exportability flags, and streaming response handling
    
    Good catches — all three are non-trivial. Let me work through each properly.
    
    ------
    
    ## 1. Non-compliant external MCP schemas
    
    In practice, MCP tool schemas from external servers fall into a spectrum of quality:
    
    ```
    tools/list reality:
      ├── Fully valid JSON Schema with types, descriptions, required fields  ← rare
      ├── Partial schema — missing descriptions, no required array          ← common
      ├── Empty object {}  — server declared a tool with no schema at all   ← frequent
      ├── Invalid JSON Schema — wrong types, unrecognized keywords           ← occasional
      └── No inputSchema field at all                                        ← happens
    ```
    
    MCP output is worse — the spec defines no output schema. Results come back as typed content blocks (`text`, `image`, `resource`, `embedded_resource`), not a JSON Schema-described object.
    
    ### Strategy: intake normalization with quality tiers
    
    On `mesh.add_mcp()`, the bridge runs every tool through a normalization pipeline before registering it as a virtual agent:
    
    python
    
    ```python
    await mesh.add_mcp(
        "npx @modelcontextprotocol/server-github",
        channel="tools.github",
        # Optional overrides for specific tools with bad schemas
        schema_overrides={
            "create-issue": {
                "input_model": GitHubCreateIssueInput,   # Pydantic model
                "output_model": GitHubCreateIssueOutput,
            }
        },
        # Fallback behavior for unoverridden tools with bad schemas
        on_bad_schema="warn",  # "warn" | "skip" | "raise"
    )
    ```
    
    The normalization pipeline assigns a `schema_quality` tier:
    
    python
    
    ```python
    class SchemaQuality(Enum):
        VALIDATED   = "validated"   # passes jsonschema meta-schema check
        NORMALIZED  = "normalized"  # was partial, SDK filled gaps
        INFERRED    = "inferred"    # was empty/missing, SDK generated passthrough schema
        OVERRIDDEN  = "overridden"  # developer supplied their own model
    ```
    
    What normalization does for each tier:
    
    python
    
    ```python
    # VALIDATED — passes through, used as-is
    {"type": "object", "properties": {"repo": {"type": "string"}}, "required": ["repo"]}
    
    # NORMALIZED — SDK fills structural gaps
    # Raw:      {"properties": {"repo": {"type": "string"}}}  ← missing type, required
    # After:    {"type": "object", "properties": {"repo": {"type": "string"}}, "required": []}
    
    # INFERRED — completely empty or missing schema
    # Raw:      {} or absent
    # After:    {"type": "object", "additionalProperties": True}
    #           + warning logged + contract flagged
    
    # OVERRIDDEN — developer supplied a Pydantic model
    # input_schema = MyInputModel.model_json_schema()
    # Full validation on ingress, clean contract in registry
    ```
    
    The `schema_quality` field lives in the contract under `x-agentmesh` and surfaces in the catalog:
    
    python
    
    ```python
    catalog = await mesh.catalog(channel="tools.github")
    # [
    #   {"name": "create-issue", "schema_quality": "overridden",  ...},
    #   {"name": "list-repos",   "schema_quality": "validated",   ...},
    #   {"name": "get-diff",     "schema_quality": "inferred",    ...},  ← caveat emptor
    # ]
    
    # Filter to only tools you trust
    catalog = await mesh.catalog(
        channel="tools.github",
        min_schema_quality="normalized"  # excludes "inferred"
    )
    ```
    
    Output side: since MCP returns untyped content blocks, the bridge always deserializes the MCP result into a normalized envelope rather than pretending it matches a JSON Schema:
    
    python
    
    ```python
    class MCPToolResult(BaseModel):
        content: list[MCPContentBlock]  # text | image | resource
        is_error: bool = False
        raw: dict  # original MCP response, always preserved
    
    class MCPContentBlock(BaseModel):
        type: Literal["text", "image", "resource"]
        text: str | None = None
        data: str | None = None  # base64 for images
        uri: str | None = None   # for resources
    ```
    
    If the developer provides an `output_model` override in `schema_overrides`, the bridge attempts to parse the MCP text content as JSON into that model, with a clean error if it fails.
    
    ------
    
    ## 2. The MCP-exportable flag
    
    Two separate concerns that look similar but aren't:
    
    - **Discoverability**: should this agent appear when an MCP client calls `tools/list`?
    - **SLA fitness**: is this agent's latency profile safe to expose over MCP's synchronous call model?
    
    ### Discoverability — registration-side flag
    
    python
    
    ```python
    @mesh.agent(
        name="summarizer",
        channel="nlp",
        description="...",
        export=["mcp"],         # explicitly MCP-exportable
    )
    
    @mesh.agent(
        name="chunk-router",
        channel="internal",
        description="...",
        export=[],              # internal only — never exported
    )
    
    @mesh.agent(
        name="invoice-parser",
        channel="finance",
        description="...",
        # export not set → inherits mesh default export policy
    )
    ```
    
    The `export` field lives in the contract under `x-agentmesh.export`. The `mesh.run_mcp()` bridge filters on it. Default policy is configurable at the mesh level:
    
    python
    
    ```python
    mesh = AgentMesh("nats://...")
    mesh.run_mcp(
        default_export_policy="opt-in",   # only export=["mcp"] agents visible
        # OR
        default_export_policy="opt-out",  # everything visible unless export=[]
    )
    ```
    
    Local dev default: `opt-out` (you own everything, expose everything). Production default: `opt-in` (explicit declaration required).
    
    ### SLA fitness — bridge-side gating
    
    MCP clients are synchronous from the caller's perspective. Claude Desktop, Cursor, etc. make a `tools/call` and block. An agent with `timeout_ms: 300000` (5 minutes — legitimate for a human-in-the-loop agent) will stall or timeout the MCP client.
    
    The bridge enforces a maximum SLA at startup:
    
    python
    
    ```python
    mesh.run_mcp(
        max_timeout_ms=30_000,     # refuse to export agents slower than this
        on_sla_violation="skip",   # "skip" | "warn" | "raise"
    )
    ```
    
    Agents that exceed the threshold are silently excluded from `tools/list` (with a startup log warning). This means an agent can be `export=["mcp"]` but still not appear if its SLA makes it unfit for the synchronous MCP model. Both conditions must be satisfied.
    
    ```
    Export policy check → SLA fitness check → appears in tools/list
    ```
    
    For `add_mcp()`, the SLA question runs in reverse: the bridge derives an SLA from observed MCP server behavior (or a developer-supplied timeout hint) and stamps it on the virtual agent contract:
    
    python
    
    ```python
    await mesh.add_mcp(
        "npx @modelcontextprotocol/server-github",
        channel="tools.github",
        sla={"timeout_ms": 15_000, "expected_latency_ms": 2_000},
    )
    ```
    
    ------
    
    ## 3. Streaming — this needs a proper design
    
    MCP streaming and NATS streaming are both real but they're different models that need explicit bridging.
    
    ### MCP streaming model
    
    MCP uses SSE progress notifications during a `tools/call`. The server can emit intermediate `notifications/progress` events before the final result. The final `tools/call` response is still a single JSON-RPC result — streaming is advisory, not the primary delivery mechanism.
    
    There's also a deeper streaming case: MCP servers can return `resource` content blocks that reference streamed data (file reads, etc.).
    
    ### NATS streaming model
    
    NATS has no built-in chunked response for req/reply. Streaming over NATS means publishing sequential messages to a well-known subject. Your spec already has `capabilities.streaming: true` in the contract — but the wire protocol for it isn't defined yet.
    
    The right primitive is a **stream subject per request**:
    
    ```
    Request:   mesh.agent.nlp.summarizer        (with X-Mesh-Stream: true header)
    Chunks:    mesh.stream.{request_id}         (N messages, each a partial response)
    Terminal:  mesh.stream.{request_id}         (final message, X-Mesh-Stream-End: true)
    ```
    
    The chunk envelope:
    
    json
    
    ```json
    Headers:
      X-Mesh-Request-Id: uuid
      X-Mesh-Stream-Seq: 3          ← sequence number, 0-indexed
      X-Mesh-Stream-End: false      ← true on final chunk
    
    Body: { "delta": "...partial text..." }   ← or whatever the agent streams
    ```
    
    ### Bridging: `add_mcp()` consuming streaming MCP
    
    ```
    External MCP server (SSE chunks)
        ↓
    MCP Bridge process
        ├── Receives SSE progress notification
        ├── Publishes to mesh.stream.{request_id}  with X-Mesh-Stream-Seq: N
        ├── Receives next chunk → publishes next message
        └── Receives final result → publishes terminal message (X-Mesh-Stream-End: true)
    ```
    
    The mesh caller that sent `mesh.call("tools.github.create-issue", ...)` can either:
    
    python
    
    ```python
    # Responder — bridge waits for all chunks, returns complete result
    # Caller sees nothing until done. Simple. Loses streaming benefit.
    result = await mesh.call("tools.github.search", payload, timeout=30.0)
    
    # Streamer — caller receives chunks as they arrive
    async for chunk in mesh.stream("tools.github.search", payload, timeout=30.0):
        print(chunk.delta)
    ```
    
    The bridge advertises whether an MCP tool streams:
    
    python
    
    ```python
    # In the virtual agent contract:
    "capabilities": {
        "streaming": True,    # MCP server sends progress notifications
        "pushNotifications": False
    }
    ```
    
    ### Bridging: `run_mcp()` exposing streaming mesh agents
    
    ```
    MCP Client (Claude Desktop)
        ↓ tools/call over SSE connection
    MCP Bridge
        ├── Sends request to mesh.agent.nlp.summarizer (X-Mesh-Stream: true)
        ├── Subscribes to mesh.stream.{request_id}
        ├── Each NATS chunk message → SSE notifications/progress event to MCP client
        └── Terminal NATS message → final tools/call JSON-RPC result
    ```
    
    The MCP client sees standard SSE progress notifications — it doesn't know or care that the underlying transport is NATS.
    
    ### What this requires added to the spec
    
    The streaming wire protocol needs a dedicated section. Key additions:
    
    ```
    mesh.stream.{request_id}    # per-request streaming subject (new)
    ```
    
    New headers:
    
    ```
    X-Mesh-Stream: true         # request-side: caller wants streaming
    X-Mesh-Stream-Seq: N        # response-side: chunk sequence number  
    X-Mesh-Stream-End: true     # response-side: no more chunks follow
    ```
    
    New SDK method:
    
    python
    
    ```python
    async for chunk in mesh.stream("agent-name", payload, timeout=30.0):
        # chunk.delta — partial content
        # chunk.seq   — sequence number
        # chunk.done  — True on final chunk
        ...
    ```
    
    And a new `capabilities.streaming` enforcement: if a caller sends `X-Mesh-Stream: true` to an agent that declared `streaming: false`, the bridge returns a `MeshError` with `code: "streaming_not_supported"` rather than silently falling back to buffered mode.
    
    ------
    
    ## Summary of what needs to land in the spec
    
    | Topic                                | Addition needed                                              |
    | ------------------------------------ | ------------------------------------------------------------ |
    | Schema quality tiers                 | `schema_quality` field in `x-agentmesh`, normalization pipeline spec |
    | `on_bad_schema` behavior             | Documented policy: warn/skip/raise + schema_overrides API    |
    | MCP output envelope                  | `MCPToolResult` as the canonical output type for bridge tools |
    | Export flag                          | `export: list[str]` on agent registration, default policy at mesh level |
    | SLA gating for `run_mcp()`           | `max_timeout_ms` filter, documented behavior                 |
    | Streaming subjects                   | `mesh.stream.{request_id}` subject convention                |
    | Streaming headers                    | `X-Mesh-Stream`, `X-Mesh-Stream-Seq`, `X-Mesh-Stream-End`    |
    | `mesh.stream()` API                  | Async generator caller-side method                           |
    | `capabilities.streaming` enforcement | Error on mismatch, not silent fallback                       |
    
    On point 2: Why an export list instead of a Boolean `mcp` attribute? Do you see other export patterns happening?
    
    11:34
    
    Weighed design tradeoffs between list and boolean approaches
    
    Honest answer: no, I don't see other meaningful export targets emerging.
    
    The list was premature generalization. The implicit reasoning was "maybe agents get exported to A2A, or some future protocol" — but that reasoning doesn't hold up:
    
    - **A2A** exposure happens at the gateway level, not per-agent. The gateway wraps the entire mesh boundary. You don't flag individual agents as "A2A-exportable" — you configure the gateway to expose a channel or namespace.
    - **MCP** is genuinely per-agent because `tools/list` is a flat enumeration. An MCP client gets every exported tool in one list, so you need per-agent control over what appears.
    - Any future protocol will almost certainly follow one of these two patterns — boundary gateway (A2A-style) or flat tool enumeration (MCP-style) — and neither requires the list to grow.
    
    So the flag should just be:
    
    python
    
    ```python
    @mesh.agent(
        name="summarizer",
        channel="nlp",
        description="...",
        mcp=True,    # appears in tools/list when run_mcp() is active
    )
    
    @mesh.agent(
        name="chunk-router",
        channel="internal",
        description="...",
        mcp=False,   # internal plumbing, never exported
    )
    ```
    
    Clean, obvious, no cognitive overhead. The `export=["mcp"]` pattern would only make sense if different agents needed different export destinations simultaneously — and that's not a real scenario since the gateway handles cross-protocol translation at the boundary, not at the agent registration level.
    
    The one thing worth preserving from the list design is the **mesh-level default policy**, since that's genuinely useful regardless of the flag shape:
    
    python
    
    ```python
    mesh.run_mcp(default_mcp=True)   # opt-out: everything exported unless mcp=False
    mesh.run_mcp(default_mcp=False)  # opt-in: nothing exported unless mcp=True
    ```
    
    That's the right place for policy configuration — not on each decorator.