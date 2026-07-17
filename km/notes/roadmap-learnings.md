# H2 2026 roadmap — learnings

Append-only, dated. Read on entry to every stage; carries what execution discovered.
If a lesson invalidates a later stage prompt in `2026-07-16-h2-roadmap-prompts.md`,
update that file too and say so here.

## 2026-07-17 — Stage 0, run 1 (cloud executor)

- **The wildfire-demo branch does not exist on origin.** Stage 0's headline item
  (merge `feature/wildfire-demo`, ~50 commits) assumed the branch was pushed; only the
  specs/ADRs are on main. The branch — and the 15 `.claude/worktrees/agent-*` worktrees —
  live only on Luca's machine. Cloud runs cannot touch either. Stage 2 (demo recording)
  depends on this code landing; flagged in the state file under Needs Luca.
- **The ty count in the prompt (67) had drifted to 245.** ty is pre-1.0 and each release
  adds rules; counts in prompts rot fast. All were fixable: about half traced to two root
  causes (a wrong `AsyncIterator` annotation on `AgentMesh.local()`, and `Client | None`
  unions poked from ~70 call sites — fixed with narrowing properties `_conn`/`kv`/`workspace`).
- **ty caught a real bug during the fix itself**: `MeshError` subclasses take keyword-only
  `message=`; a positional call raised TypeError only on the error path. Type checking the
  error paths pays off precisely because tests rarely exercise them.
- **The ADR-0031 streamer convention conflicts with strict typing.** Async-generator
  handlers annotate the chunk type as the return type (schema inference reads it). ty
  rightly flags every such handler; suppressed `invalid-return-type` for `tests/**` and
  `demos/**` with rationale in pyproject. Candidate future ADR: also accept
  `AsyncIterator[Chunk]` annotations in `inspect_handler` so typed user code checks clean.
- **Cloud env: GitHub release downloads are blocked (403) by the network policy**, so
  `AgentMesh.local()`'s embedded-NATS download fails. Workaround that works:
  `go install github.com/nats-io/nats-server/v2@v2.10.24` (proxy.golang.org is allowed),
  copy to `~/.agentmesh/bin/`. Every future cloud run needs this before pytest/vitest.
- **The sdk-ts flake was a missing flush**, as suspected: sim helpers subscribed but never
  flushed before tests invoked agents on a second connection. Making the registration
  helpers async (flush inside) fixed it; 5 consecutive full runs green. Related JS footgun
  found while fixing: `await` recursively unwraps a returned `Promise<Msg>`, so a helper
  returning a capture promise must wrap it in an object or the caller deadlocks.
- **The "map pydantic ValidationError" gap in the prompt was stale**: ADR-0057 already
  maps `ValidationError` → `InvalidInput` (`invalid_input` on the wire), and docs agree.
  Verified in `_mesh.py` before writing any code — the "trust the repo" rule earned its keep.
- Two stale remote branches (`feature/error-taxonomy`, `feature/tool-conversion`) predate
  their content landing on main (verified: main has the tests/modules, branches are behind).
  Deletion is destructive → left for Luca.

## 2026-07-17 — Stage 1, run 2 (cloud executor)

- **Two executor runs overlapped.** Run 2's cron fired while run 1 was still pushing;
  both did the same ty work in parallel and run 2 threw its duplicates away. Proposed
  lock protocol for future runs: before starting work, check `git log -1 --format=%ci`
  on origin/main and any roadmap/* branch — if the newest commit is less than ~15 min
  old, assume a sibling run is live: re-fetch every few minutes and only proceed once
  origin has been quiet for 15 min (or limit yourself to read-only verification).
  Never force-push a roadmap branch; on divergence, adopt origin and diff for anything
  yours adds.
- **The MCP SDK validates tool arguments client-side** against inputSchema before the
  server sees the call, so ADR-0057 caller faults (invalid_input) rarely reach the mesh
  through the bridge. Provider faults do: the bridge prefixes tool errors with the
  taxonomy code (e.g. `handler_error: ...`).
- **`mcp.shared.memory.create_connected_server_and_client_session` gives a genuine
  client↔server protocol exchange without subprocesses** — ideal for cookbook twins.
  The stdio subprocess e2e (`python -m openagentmesh.cli mcp serve`) adds only ~1.5 s
  and proves the real transport.
- **mesh.contract() had been silently dropping input/output schemas** on the registry
  round-trip (skills[0].inputSchema was never mapped back). Local contracts masked it
  (`self._agents` short-circuit). Found because the bridge's remote-agent test showed
  an empty tool schema. Cross-process tests catch what single-process tests structurally
  cannot; worth a chaos-style two-process test pass someday (Stage 3 candidate).
- **pytest module basename collision:** tests/test_mcp_bridge.py vs
  tests/cookbook/test_mcp_bridge.py broke collection (no __init__.py in test dirs).
  Cookbook twins keep the recipe name; give root tests a distinct name.
- **Registration is lazy** (contracts publish on the next mesh operation, not at
  decoration). A gateway connecting to a fresh host sees nothing until the host flushes.
  Fine for real deployments (serve_mcp enters the mesh context), but multi-connection
  tests need a warmup call. DX question for later: should @mesh.agent on a connected
  mesh subscribe eagerly?
