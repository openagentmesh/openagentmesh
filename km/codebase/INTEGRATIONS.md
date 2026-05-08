# External Integrations

**Analysis Date:** 2026-05-08

## APIs & External Services

**Message Bus / Service Fabric:**
- NATS - Distributed messaging, event streaming, and key-value store
  - SDK/Client: nats-py 2.14.0+
  - What it's used for: Core communication substrate. Agents publish/subscribe via NATS subjects; discovery and catalog stored in NATS KV; handler registration via NATS subscriptions
  - Endpoint: Configurable via `OAM_URL` env var, CLI flag `--url`, or `.oam-url` file
  - Default: `nats://localhost:4222`
  - Auth: No auth mechanism in Phase 1 MVP (ADR scope: federation auth deferred to Phase 2+)

**LLM Integration (Optional, Demo Only):**
- OpenAI - For demo recipes (not required for SDK core)
  - SDK/Client: openai 1.0.0+ (in `demo` dependency group, optional)
  - What it's used for: LLM-based agent selection and orchestration in demo scripts
  - Auth: OPENAI_API_KEY (not checked by SDK; left to demo user to provide)
  - Location: `src/openagentmesh/demos/llm_tool_selection.py` (recipe only; no actual OpenAI calls in current Phase 1)
  - Note: OpenAI integration is aspirational in cookbook docs; actual recipes use mock LLM selection logic

## Data Storage

**Message Queue & Distributed Registry:**
- NATS JetStream - Event streaming for agent-to-agent messages
  - Connection: Same NATS URL (`OAM_URL`)
  - Used for: `mesh.stream()`, `mesh.subscribe()`, `mesh.send()` — message delivery guarantees

- NATS KeyValue - Distributed key-value store for catalog and agent contracts
  - Connection: Same NATS URL (`OAM_URL`)
  - Buckets:
    - `mesh-catalog` - Global catalog of registered agents (read by all agents)
    - `mesh-registry` - Per-agent contract schemas (read by discovery, write by registration)
    - `mesh-context` - Invocation context and state (experimental, not finalized in Phase 1)
    - `mesh-artifacts` - Workspace objects (future use)
  - Client: nats-py KeyValue interface via `AgentMesh._registry_kv`, `AgentMesh._catalog_kv`

**File Storage:**
- Workspace Object Store (embedded in NATS, unused in Phase 1)
  - Location: `src/openagentmesh/_workspace.py` (placeholder)
  - Future use: Artifact storage for agents (e.g., large outputs, files)

**Caching:**
- In-memory catalog cache on `AgentMesh` instance
  - Location: `src/openagentmesh/_mesh.py` (field: `_catalog_cache`)
  - Invalidation: Via NATS KV watcher watching catalog bucket changes
  - Rationale: Avoid repeated KV fetches for catalog; watch for updates asynchronously

## Authentication & Identity

**Auth Provider:**
- None (not implemented in Phase 1 MVP)
- Deferred to Phase 2+ (federation and cross-org scenarios)
- Current scope: Single NATS cluster, no per-agent auth

**Current Approach:**
- Agent identity: Agent name (e.g., `"finance.risk.scorer"`) + subject
- Discovery: Catalog browsing and contract fetching are unauthenticated
- Invocation: Direct NATS request-reply; no token verification

## Monitoring & Observability

**Error Tracking:**
- None (no integration with Sentry, Datadog, etc.)
- Phase 1 uses structured error taxonomy (ADR-0057)
- Location: `src/openagentmesh/_errors.py` (error classes: MeshError, ConnectionFailed, HandlerError, etc.)

**Logs:**
- Approach: Python stdlib `logging` module
- Loggers:
  - `"openagentmesh"` - Main SDK logger
  - Used in: `src/openagentmesh/_mesh.py` (line 43)
  - Output: Sent to stderr by default; caller controls handlers and level
  - Current output: Print statements for demo feedback (e.g., "[openagentmesh] embedded NATS at nats://127.0.0.1:XXXX")

**Tracing:**
- Not implemented (no OpenTelemetry integration in Phase 1)
- Future consideration: ADR-0038 (deferred)

## CI/CD & Deployment

**Hosting:**
- Not determined (Phase 1 focuses on local dev and embedded NATS)
- Assumption: NATS cluster deployed separately (on Kubernetes, Docker, etc.)
- SDK is a Python library; deployment is user's responsibility

**CI Pipeline:**
- GitHub Actions workflow (if any) - not scanned in this analysis
- Test command: `pytest` (runs against embedded NATS via `AgentMesh.local()`)
- Lint/Format: `ruff check src/ tests/` and `ruff format`

## Environment Configuration

**Required env vars:**
- None (all config is optional; defaults are sensible)

**Optional env vars:**
- `OAM_URL` - NATS server URL (default: `nats://localhost:4222`)
  - Resolution precedence (ADR-0033):
    1. CLI flag `--url`
    2. Env var `OAM_URL`
    3. `.oam-url` file (walked up directory tree from cwd)
    4. Default: `nats://localhost:4222`

**Secrets location:**
- Not applicable in Phase 1 (no auth, no API keys)
- Assumption: If external NATS requires auth, it's configured at NATS level, not SDK level

## Network & Transport

**Protocol:**
- NATS (nats:// or nats+tls:// with TLS support in nats-py, but not used in Phase 1)
- Default port: 4222

**Subjects (Messaging Schema):**
- Format: `mesh.agent.<agent_name>.{call|stream|subscribe}.<request_id>`
- Examples:
  - `mesh.agent.echo.call.12345` - Call request to echo agent
  - `mesh.agent.orchestrator.stream.67890` - Stream subscription
- Error subjects: `mesh.agent.<agent_name>.error.<request_id>`
- Generated by: `src/openagentmesh/_subjects.py` (compute_subject, compute_error_subject, etc.)

## Webhooks & Callbacks

**Incoming:**
- None (not applicable; agents don't expose HTTP endpoints in Phase 1)
- All communication is NATS-native

**Outgoing:**
- None (agents don't call external webhooks)
- Demo recipes can call external APIs (e.g., OpenAI) directly from handler code, but this is user responsibility, not SDK concern

## Binary Downloads

**NATS Server:**
- Source: GitHub releases (https://github.com/nats-io/nats-server/releases)
- Version: 2.10.24 (pinned)
- Trigger: `AgentMesh.local()` or `agentmesh up`
- Download method: curl (system command)
- Extraction: tar/zip (system commands)
- Cache location: `~/.agentmesh/bin/nats-server`
- Platforms: darwin/linux/windows, amd64/arm64

## Documentation

**Build Tool:**
- zensical (0.0.32+) - Markdown to static HTML
- Config: `mkdocs.yml`
- Source: `docs/` directory
- Output: `site/` (gitignored)
- Dev server: `uv run zensical serve`

---

*Integration audit: 2026-05-08*
