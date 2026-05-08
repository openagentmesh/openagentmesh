# Codebase Concerns

**Analysis Date:** 2026-05-08

## Tech Debt

**Hard NATS reconnection disabled on mesh connection failure:**
- Issue: `AgentMesh._connect()` at `src/openagentmesh/_mesh.py:122-127` disables NATS reconnection with `allow_reconnect=False`, meaning a single network glitch terminates the mesh client permanently. The agent must be restarted to recover. This is acceptable for short-lived scripts but problematic for long-running service deployments.
- Files: `src/openagentmesh/_mesh.py` (lines 122-127)
- Impact: Production deployments lose mesh connectivity on any network hiccup. Orchestrators expecting mesh agents to self-heal will timeout waiting for responses from agents that have already disconnected but remain alive.
- Fix approach: Swap `allow_reconnect=False` to `allow_reconnect=True` and tune `max_reconnect_attempts` / `reconnect_time_wait` based on deployment context (local dev vs. network). Consider making this configurable via `AgentMesh(url=..., reconnect=True)`.

**Catalog update CAS loop has loose upper bound on retries:**
- Issue: `AgentMesh._update_catalog()` at `src/openagentmesh/_mesh.py:715-746` retries catalog updates up to 10 times with 10ms backoff on CAS collision, but if the catalog is under sustained concurrent updates from many agents, this loop can exhaust and raise `RuntimeError: Failed to update catalog after 10 CAS retries`. The recovery strategy is not defined.
- Files: `src/openagentmesh/_mesh.py` (lines 721-746)
- Impact: Mesh startup with many concurrent agents (>20) registering simultaneously may fail partially, leaving some agents unregistered while the error is silently caught in `_subscribe_pending()` or `_shutdown()`. This creates silent registration failures.
- Fix approach: Increase retry count and use exponential backoff instead of fixed 10ms. Log a warning and fail-safe: either retry indefinitely with jitter, or make catalog update failures fatal at startup (let the agent crash rather than register partially).

**Publisher/Publisher emission has no backpressure handling:**
- Issue: `AgentMesh._emit_publisher_events()` at `src/openagentmesh/_mesh.py:588-651` publishes each yielded chunk via `_nc.publish()` without awaiting flow control. If the publisher yields faster than NATS can deliver (slow subscribers or large payloads), the publish queue grows unbounded, consuming memory.
- Files: `src/openagentmesh/_mesh.py` (lines 603-610)
- Impact: Long-running publishers that yield high-frequency events (>1000/sec) risk OOM crashes. No mechanism to slow down the generator or apply backpressure.
- Fix approach: Add a bounded async queue between the generator and publisher. If the queue fills, wait (apply backpressure to generator). Alternatively, batch chunks and flush periodically.

**Object Store cleanup gaps are unresolved (ADR-0027 discussion status):**
- Issue: ADR-0027 identifies three cleanup patterns for `mesh-artifacts` but remains in `discussion` status. Currently the SDK exposes only `put`, `get`, `watch`, `delete` — no batch delete by prefix, no session scoping, no revision history access.
- Files: `km/adr/0027-object-store-workspace-lifecycle-and-scoping.md`
- Impact: Multi-step workflows that create intermediate artifacts must manually delete each one or accept unbounded storage growth. No way to query revision history for incremental artifact pipelines without manual key-naming conventions.
- Fix approach: Implement Option B (expose `history()` and `get_revision()`) or Option D (add `delete_prefix()` helper). Option B is more powerful; Option D is simpler for Phase 1.

**No control-plane scoping or agent lifecycle gates (ADR-0035, ADR-0055 spec/discussion status):**
- Issue: Once agents register, they are universally discoverable and invocable by any caller. No mechanism to pause, drain, or disable agents at runtime. ADR-0035 and ADR-0055 remain in spec/discussion, so these features are deferred.
- Files: `km/adr/0035-control-plane-for-agent-channel-scoping.md`, `km/adr/0055-agent-lifecycle-gates.md`
- Impact: Operators cannot take agents offline for maintenance or canary rollouts without restarting the process. Multi-team meshes have no visibility isolation — all agents see all other agents.
- Fix approach: Implement ADR-0055 (lifecycle gates with `active_when` conditions) for local control, then ADR-0035 for global scoping. Both are deferred to Phase 2+.

## Known Bugs

**Streaming timeout calculation uses deprecated asyncio pattern:**
- Symptoms: `mesh.stream()` at `src/openagentmesh/_invocation.py:113-117` uses `asyncio.get_event_loop().time()` twice in a loop, which can be slow on systems with many event loops or in certain asyncio implementations. Not a bug per se, but fragile.
- Files: `src/openagentmesh/_invocation.py` (lines 113-118)
- Trigger: Long streaming sessions with many intermediate timeouts
- Workaround: Use `asyncio.wait_for()` directly without manual deadline calculation. The current implementation is correct but suboptimal.

**NATS embedded server download does not verify checksums:**
- Symptoms: `EmbeddedNats.download_nats_server()` at `src/openagentmesh/_local.py:37-94` curls the NATS binary from GitHub releases but does not verify GPG signatures or SHA256 checksums. A compromised release or MITM attack could inject malicious code into the development environment.
- Files: `src/openagentmesh/_local.py` (lines 37-94)
- Trigger: Running `AgentMesh.local()` for the first time on a system without a pre-downloaded NATS binary
- Workaround: Use `agentmesh up` with a pre-installed NATS binary instead of relying on auto-download (ADR-0015 prefers PATH over download)

## Security Considerations

**NATS connection allows unauthenticated clients by default:**
- Risk: The embedded NATS server (`AgentMesh.local()`) and the `agentmesh up` CLI start NATS with no authentication. Any process that can reach the port can connect and invoke agents. No secrets are required.
- Files: `src/openagentmesh/_local.py`, `src/openagentmesh/cli/mesh.py`
- Current mitigation: Embedded server binds to `127.0.0.1` only (localhost). The operational server assumes network-level access control (VPN, firewall, private subnet). This is acceptable for local development and team-internal deployments but insufficient for multi-tenant or untrusted-network scenarios.
- Recommendations: (1) For production deployments, mandate NATS authentication via ADR-0038 (when implemented). (2) For embedded servers, document that they are single-host only and never expose to untrusted networks. (3) Add a warning log when NATS starts without auth.

**No input validation of agent names at registration time:**
- Risk: Agent names are used directly in NATS subject construction. A malicious or buggy agent name could inject subject wildcards or special characters, breaking subject routing.
- Files: `src/openagentmesh/_mesh.py` (agent decorator)
- Current mitigation: ADR-0049 introduced name validation at registration time (`[a-zA-Z0-9_-]+` segments), but this is not fully visible in the codebase. Verify that `AgentSpec` enforces it at construction time.
- Recommendations: (1) Add explicit validation in `AgentMesh.agent()` decorator before registration. (2) Document the naming convention clearly in the API reference.

**Object Store (mesh-artifacts) has no access control:**
- Risk: Any agent on the mesh can read, write, or delete any object in `mesh-artifacts`. No per-object or per-agent permissions.
- Files: `src/openagentmesh/_workspace.py`, NATS Object Store bucket
- Current mitigation: Trust boundary is the network perimeter (same as NATS itself). This is acceptable for single-team deployments.
- Recommendations: (1) For multi-team meshes, layer a secondary auth mechanism (e.g., KV-based ACLs that agents check before reading sensitive artifacts). (2) When NATS accounts are implemented (ADR-0038), use account-level subject permissions to isolate artifact buckets by team.

## Performance Bottlenecks

**Catalog watcher re-parses entire catalog on every update:**
- Problem: `AgentMesh._start_catalog_watcher()` at `src/openagentmesh/_mesh.py:190-211` watches the single `catalog` KV key. Each time any agent registers/deregisters, the entire catalog (JSON list of all agents) is re-parsed and the cache is rebuilt. With 500+ agents, this is O(n) per update.
- Files: `src/openagentmesh/_mesh.py` (lines 202-204)
- Cause: The catalog is stored as a single denormalized KV value (ADR-0014) for simplicity. Scalability is a known tradeoff.
- Improvement path: (1) For Phase 1 (target ~100 agents), the current design is acceptable. (2) For Phase 2+, consider per-agent KV entries with a metadata index, or move to a tiered discovery model where only frequently-queried agents are cached.

**LLM-based agent selection with full catalog JSON:**
- Problem: `mesh.catalog()` returns all agents for the caller to pass to an LLM for tool selection. With 500 agents at ~500 bytes each, the JSON context is ~250KB, which consumes 10-15K tokens in an LLM call.
- Files: `src/openagentmesh/_discovery.py`
- Cause: ADR-0009 chose catalog-as-sole-primitive for simplicity. Scaling to many agents requires filtering or summarization.
- Improvement path: (1) Add optional `catalog(filter=...)` parameter to tag agents by domain and reduce results. (2) Implement ADR-0035 scoping to limit discoverable agents per caller. (3) For very large meshes (>1000 agents), use a secondary ML-based retrieval layer (not part of Phase 1).

**Cascade retry storms on shared agent timeouts:**
- Problem: If a single popular agent (e.g., orchestrator) goes down, all callers timeout simultaneously and retry. With many callers, this creates a thundering herd of retries, overloading the mesh when the agent restarts.
- Files: Across `src/openagentmesh/_invocation.py` call/stream/send
- Cause: No built-in retry logic or exponential backoff in the SDK. Callers implement their own or experience cascade failures.
- Improvement path: (1) Add optional exponential backoff to `call(retry=True, max_attempts=3, backoff=...)`. (2) Implement ADR-0040 (death-notice fast-fail) to notify callers immediately when an agent dies, rather than timing out.

## Fragile Areas

**Shutdown sequence is fragile to exceptions at each step:**
- Files: `src/openagentmesh/_mesh.py` (lines 213-299)
- Why fragile: The shutdown method has 6 sequential steps, each wrapped in try/except that swallows all exceptions. If step 3 (cancel handlers) crashes, steps 4-6 still execute, but step 3's cleanup may be incomplete. The code tolerates this ("broken connection is the common case"), but silent failures can mask serious issues.
- Safe modification: (1) Assign each step a name and log it as it completes. (2) Separate fatal failures (e.g., step 1 catalog watcher crash) from expected exceptions (e.g., connection already closed). (3) Add a `_shutdown_errors` list and log them at the end.
- Test coverage: `tests/test_mesh.py` has integration tests but may not cover edge cases like shutdown during concurrent invocations.

**Handler execution path has multiple error transformation points:**
- Files: `src/openagentmesh/_mesh.py` (lines 437-502)
- Why fragile: Invocation mismatch, validation error, and handler error are all caught and transformed to `MeshError` subclasses. If a handler raises an exception that is not a `MeshError` (line 473), it is wrapped as `HandlerError`. If that wrapping itself fails, the error path publishes an error message (lines 483-502). If the publish fails, it is swallowed (caught in the handler).
- Safe modification: (1) Add structured logging at each error transformation so exceptions are not lost. (2) Unit test the error paths independently from the NATS publish path.
- Test coverage: `tests/test_errors_taxonomy.py` covers error serialization; `tests/cookbook/test_error_handling.py` covers handler errors in context.

**Subscription cleanup does not wait for pending messages:**
- Files: `src/openagentmesh/_invocation.py` (lines 103-205 for stream(), lines 186-205 for subscribe())
- Why fragile: When `finally: await sub.unsubscribe()` is called, any messages already delivered to the handler callback but not yet consumed from the queue are lost. For fast producers and slow consumers, this can drop the last chunk of a stream.
- Safe modification: (1) Keep the subscription open while draining the queue. (2) Add a grace period before unsubscribing. (3) For streaming, explicitly wait for `X-Mesh-Stream-End` before closing.
- Test coverage: `tests/test_subscribe.py` tests subscribe patterns but may not cover edge cases like unsubscribe with pending messages.

**Catalog cache can become stale during network partition:**
- Files: `src/openagentmesh/_mesh.py` (lines 190-211, catalog watcher)
- Why fragile: If the NATS connection breaks, the catalog watcher task is cancelled and the cache freezes at its last known state. A caller using `mesh.contract(name)` will see stale results until the connection recovers. The SDK does not explicitly handle this.
- Safe modification: (1) Tag catalog entries with a timestamp and mark stale entries after a timeout. (2) On contract miss, raise an explicit `StaleCache` or `CatalogUnavailable` error rather than proceeding with stale data. (3) Log when the watcher reconnects and the cache refreshes.
- Test coverage: Integration tests do not cover network partitions; this would require mock NATS or test fixture that can simulate disconnection.

## Scaling Limits

**Catalog size is O(n) for discovery and O(n) for every agent update:**
- Current capacity: Tested up to ~100 agents; catalog entry is ~500 bytes, so ~50KB total.
- Limit: At ~500 agents, catalog JSON is ~250KB per update, LLM context for tool selection exceeds 10K tokens, and the denormalized KV update becomes a bottleneck.
- Scaling path: (1) Implement ADR-0035 scoping so agents only see relevant peers. (2) Add `catalog(filter=...)` to reduce results by domain tag. (3) For >1000 agents, migrate to a multi-level discovery model (local cache + remote index).

**NATS embedded server single-process, no persistence:**
- Current capacity: `AgentMesh.local()` runs NATS in-process for tests/demos. This is a single event loop with no replication.
- Limit: Suitable for <10 concurrent agents in tests. Not suitable for production workloads.
- Scaling path: (1) For production, use standalone `agentmesh up` (still single-process by default). (2) For HA, run a NATS cluster (outside the scope of OAM SDK). (3) See NATS deployment docs for cluster/JetStream replication setup.

**KV and ObjectStore buckets have no quota enforcement:**
- Current capacity: `mesh-context` and `mesh-artifacts` buckets are created with default NATS settings (no size limit, no TTL).
- Limit: A runaway workflow that writes unbounded artifacts to `mesh-artifacts` will eventually consume all disk space on the NATS server.
- Scaling path: (1) Document recommended TTL and max size settings in the spec (ADR-0021 left this open). (2) Add optional quota parameters to `AgentMesh(..., artifacts_quota=..., context_ttl=...)`. (3) For production, configure bucket limits in the NATS server config.

## Dependencies at Risk

**nats-py is the only runtime dependency; no fallback transport:**
- Risk: If nats-py introduces a breaking change or critical bug, the entire SDK is blocked. There is no abstraction layer to swap in a different transport.
- Impact: Any incompatibility with a new NATS server version or Python release must be fixed directly in nats-py or the SDK.
- Migration plan: (1) Keep nats-py version constraints loose (`>=2.14.0`) to allow bug fixes. (2) Monitor NATS release notes for breaking changes. (3) Consider a transport abstraction layer if multi-protocol support becomes a requirement (deferred).

**pydantic v2 is the validation and JSON schema source; no alternatives:**
- Risk: A security issue in Pydantic or a breaking API change affects all contract schemas and input/output validation.
- Impact: Must track Pydantic releases and test compatibility with new major versions before adopting.
- Migration plan: (1) Keep Pydantic version constraint permissive (`>=2.12.5`). (2) Test each new minor release in CI before declaring support. (3) Document minimum supported Pydantic version in the README.

**Python 3.11+ only; no support for 3.10 or earlier:**
- Risk: Some deployments (legacy infrastructure, containers) may be stuck on Python 3.10. No compatibility path.
- Impact: Early-bird adopters on older Python versions cannot use OAM without upgrading.
- Migration plan: (1) Document Python 3.11+ as a hard requirement. (2) If 3.10 support is requested, evaluate the effort to backport (likely minimal — async/await is stable). (3) Accept that 3.9 and earlier will not be supported due to asyncio changes.

## Missing Critical Features

**No built-in retry logic or exponential backoff:**
- Problem: Callers must implement their own retry loops. The SDK provides no utilities. This leads to inconsistent retry behavior across agents and potential cascade failures.
- Blocks: Error-tolerant orchestration patterns; graceful degradation under load.
- Fix: Add `mesh.call(..., retry=True, max_attempts=3, backoff_ms=100, backoff_multiplier=1.5)` with exponential jitter.

**No observability/tracing hooks (ADR-0048 discussion status):**
- Problem: No built-in logging of invocations, latency metrics, or trace context propagation. Operators cannot see mesh health without external instrumentation.
- Blocks: Production ops; SLA monitoring; flame graph profiling.
- Fix: Implement ADR-0048 (structured logging and tracing on NATS subjects). Start with basic latency logging, then add OpenTelemetry integration.

**No liveness probes or health checks (ADR-0040 discussion status):**
- Problem: No way to distinguish a zombie agent (process alive but unresponsive) from a crashed agent. Heartbeat detection requires 30s timeout by default.
- Blocks: Fast failure and recovery; SLA guarantees.
- Fix: Implement ADR-0040 (death notices via NATS disconnect advisories) and periodic health checks.

## Test Coverage Gaps

**Concurrent catalog updates are not stress-tested:**
- What's not tested: Simultaneous registration of 50+ agents with concurrent catalog updates
- Files: `tests/test_mesh.py` (integration tests)
- Risk: The CAS retry loop may fail under high concurrency, leading to partial registration or silent failures
- Priority: Medium — impacts large deployments; Phase 1 target is ~10 agents

**Network partition handling is not tested:**
- What's not tested: NATS disconnect, reconnect, and catalog recovery scenarios
- Files: `tests/test_mesh.py`
- Risk: Edge cases in the catalog watcher or connection recovery logic remain hidden until production
- Priority: High — these are failure modes that will occur in any distributed deployment

**Streaming timeout edge cases are not covered:**
- What's not tested: Stream timeout, slow producer, subscriber disconnect mid-stream
- Files: `tests/test_subscribe.py`
- Risk: Corner cases in the chunk sequencing and timeout logic may cause hangs or data loss
- Priority: Medium — affects long-running streaming patterns

**Object Store revision semantics are not tested:**
- What's not tested: Overwriting an artifact multiple times and retrieving revision history (once ADR-0027 is implemented)
- Files: `tests/test_workspace.py`
- Risk: The Workspace API does not yet expose revision history, but once it does, this needs comprehensive testing
- Priority: Low — feature not yet implemented

**CLI command isolation is not tested:**
- What's not tested: Running multiple `agentmesh up` instances on the same port; cleanup after crash
- Files: `tests/cli/test_integration.py`
- Risk: Port conflicts or stale PID files during concurrent CLI runs could corrupt the development experience
- Priority: Medium — developers will run `agentmesh up` frequently and expect clean state

---

*Concerns audit: 2026-05-08*
