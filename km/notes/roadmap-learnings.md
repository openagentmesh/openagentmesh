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

## 2026-07-17 — Stage 3, run 5 (cloud executor)

- **A JWT/operator-mode nats-server refuses to start JetStream without a
  system account** (`system account not setup` at boot). Since OAM requires
  JetStream, ADR-0038's "does `oam auth init` create a system account?" open
  question is not a choice — it must. Recorded in the ADR.
- **nats-py needs the `nkeys` package for `.creds` auth** (lazy import at
  connect). Added as a core dependency; without it the failure is a raw
  `ModuleNotFoundError` mid-connect.
- **Static nsc-generated credentials + a MEMORY resolver with
  `resolver_preload` make JWT auth fully testable offline**: no nsc at test
  time, no resolver directory, JWTs never expire by default. nsc itself
  installs in the sandbox via `go install github.com/nats-io/nsc/v2@latest`
  (same Go-proxy trick as nats-server).
- **Runtime NATS permission violations are asynchronous**: the server sends
  them on the error callback and does not fail the offending publish, so a
  denied `mesh.call()` manifests as a timeout plus an async warning. True
  call-site `connection_denied` errors need request-correlation machinery —
  same machinery as the ADR-0016/0040 liveness work; noted in the ADR to
  revisit there.
- **Run 4 was cut off before it could log its run entry or create its
  branch** — the state file claimed "executing on roadmap/stage-3" but the
  branch didn't exist. Protocol tweak honored this run: commit the run-log
  entry and push the branch EARLY (branch created and pushed before the
  first code commit), so a cut-off leaves breadcrumbs instead of claims.

## 2026-07-17 — Stage 2, run 3 (cloud executor)

- **The docs URL split is an active bug, not future polish.** mkdocs.yml's
  `site_url: openagentmesh.dev` means the deployed github.io site emits canonical
  URLs and a sitemap pointing at a domain with no CNAME in the repo. Whatever Luca
  decides, the one-line site_url fix should not wait for the launch stage's other
  items. (Sandbox proxy 403s outbound web requests, so DNS state of
  openagentmesh.dev could not be checked from the cloud.)
- **Launch messaging hook that emerged from Stages 0–1:** the MCP bridge one-liner
  (`claude mcp add mesh -- oam mcp serve`) is the sharpest demoable claim — it turns
  "abstract fabric" into "your whole mesh is a toolbox for Claude in two commands."
  Both drafts and the README fold lead with it alongside the MCP/A2A gap framing
  from the competitors note ("the wire, not the workflow").
- **CI is fast enough to gate docs-only merges** (~45 s wall with the cached NATS
  binary and uv cache), so the "merge only when branch tests pass" rule costs
  nothing even for km/-only changes. No path filters in ci.yml — a green run means
  ruff/ty/pytest/tsc/vitest all actually executed; verified at job-step level once,
  future runs can trust conclusion=success.
- **ADR-0056 (admin UI) has a hidden Stage 3 dependency:** the registry screen's
  liveness indicator wants ADR-0016 disconnect advisories; building the UI before
  the liveness work means shipping a heartbeat stand-in and reworking it. Deferral
  proposed to Luca; if approved, Stage 3's plan should slot the UI after 0016/0040.
