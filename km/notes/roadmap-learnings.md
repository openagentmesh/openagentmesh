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
- **Design-derived permission lists don't survive contact with the wire.**
  ADR-0038's role table was written from the subject taxonomy; a credential
  built from it couldn't even complete registration (catalog CAS writes need
  `$KV.mesh-catalog.>` publish; KV *reads* need `$JS.API.>` publish even for
  observers). Lesson for 0016/0048: derive any subject list from a running
  mesh with a real credential, not from the docs. The e2e test that boots a
  server from the emitted config is what caught every gap.
- **The auth work surfaced a latent taxonomy leak:** `mesh.call()` timeouts
  raised raw `nats.errors.TimeoutError`, never `MeshTimeout`. Denied
  publishes also read as timeouts because NATS reports violations async on
  the error callback; the SDK now records denied subjects and converts the
  timeout at the call site into `ConnectionDenied`.
- **CI test-ordering trap:** tests/cli/* collect before tests/test_*.py, so
  anything using `find_nats_server()` directly runs before a `local()` test
  has lazily downloaded the binary. CI now installs nats-server (and nsc)
  explicitly in the python job; local sandbox runs already do this via the
  Go-proxy workaround.
- **Run 4 was cut off before it could log its run entry or create its
  branch** — the state file claimed "executing on roadmap/stage-3" but the
  branch didn't exist. Protocol tweak honored this run: commit the run-log
  entry and push the branch EARLY (branch created and pushed before the
  first code commit), so a cut-off leaves breadcrumbs instead of claims.

## 2026-07-18 — Stage 3, run 6 (cloud executor): ADR-0016/0040 liveness

- **A default no-auth nats-server cannot serve `$SYS` events at all** —
  clients land in the global account and there is no system-account user to
  log in as. The fix that preserves open-by-default DX: an accounts config
  with `no_auth_user` mapping anonymous clients to an APP account
  (JetStream enabled per-account) plus a password-protected SYS user for
  the monitor. Anonymous `AgentMesh()` connections work exactly as before.
- **Accounts isolate subjects both ways**, so the monitor needs two
  connections: SYS for advisories, APP for KV cleanup and death notices.
  One credential cannot do both without export/import plumbing.
- **Disconnect advisories only carry the connection name**, so correlation
  must be designed in: connections self-name `oam-host-{instance_id}` and a
  `mesh-instances` KV bucket maps instance → served agents. That bucket
  also fixed a latent bug: graceful shutdown of one replica used to remove
  the shared catalog entry while other replicas still served the agent.
- **Measured detection latency: 15ms** from SIGKILL to death notice through
  the real `oam mesh up` + companion monitor (sandbox e2e). The chaos test
  asserts <10s against a 30s timeout to stay CI-safe; observed ~1s
  end-to-end in pytest including registration polling.
- **A cookbook twin had pinned a leaked exception as the contract**
  (`pytest.raises(NoRespondersError)`) while the recipe prose promised
  `NotFound`. When docs and tests disagree, the docs were the intent —
  ADR-0040's no-responders mapping made the recipe true and the test
  needed the fix, not the SDK behavior preserved.
- **New wire surfaces must ship with role-template updates in the same
  change**: the mesh-instances bucket and mesh.death.> subjects broke
  freshly-minted worker/invoker creds until added to ROLE_TEMPLATES
  (`$KV.mesh-instances.>` pub/sub for workers, `mesh.death.>` sub for
  invoker/observer). Old credentials degrade gracefully — instance
  recording logs a warning instead of failing the host. Lesson repeats run
  5's: derive permission lists from the wire, and grep ROLE_TEMPLATES
  whenever adding a subject or bucket.
- **`asyncio.wait` on {request task, death future} is enough** for the
  fast-fail race — no per-target subscription sharing needed at current
  scale; noted in ADR-0040 as future work if callers get hot.

## 2026-07-18 — Stage 3, run 8 (cloud executor): ADR-0055 lifecycle gates

- **nats-py `Subscription.drain()` is not cancellation-safe.** Its flush
  roundtrip registers a pong future; cancelling the drain mid-flush leaves
  that future cancelled-but-registered, and the next PONG crashes the
  client's read loop (`InvalidStateError` in `_process_pong`) — after which
  every pending request on that connection hangs forever. Symptom was a
  test-suite hang *at shutdown* (catalog CAS get never returning), two
  tests apart from the cause. Fix: never wrap `sub.drain()` in
  `wait_for`; gated agents dispatch handlers as tracked asyncio tasks so
  deactivation is `unsubscribe()` (instant, safe) + `asyncio.wait` on our
  own task set. Same applies anywhere a drain might be cancelled (e.g. by
  `_shutdown` cancelling a background task mid-drain).
- **`unsubscribe()` kills in-flight inline callbacks.** nats-py awaits the
  subscription callback inside `_wait_for_msgs`, and `unsubscribe()`
  cancels that task — so drain-then-complete semantics REQUIRE handlers to
  run as separate tasks. Worth remembering if ungated agents ever need
  graceful per-agent teardown.
- **Debugging a loop-idle hang: dump `asyncio.all_tasks()` from a
  standalone repro**, not py-spy (py-spy shows the thread parked in
  `select`, which says nothing). A wrapper script with
  `asyncio.wait_for(main(), N)` + task-stack dump on timeout found the
  poisoned-connection chain in one run.
- **Two test races worth pattern-matching:** (1) a warm-up call that sets
  the same "handler entered" Event the real assertion waits on — clear the
  event after warm-up or the test proceeds before the real request is in
  flight; (2) a request published in the instant a gate closes can be
  dropped (interest existed at publish, gone at delivery) → the caller
  gets a timeout, not no-responders. The second is real wire semantics,
  now documented in concepts/lifecycle.md: treat both `not_available` and
  a timeout during a gate transition as retryable.
- **The ADR-as-written had a self-contradictory mechanic** ("drain-phase
  callers receive not_available" from an agent that just left its queue
  group and cannot reply). Caller-side mapping (no-responders + still in
  catalog → `not_available`) implements the intent cleanly and also covers
  the fully-offline state. Shaping check that caught it: for every
  proposed error path, ask *which process sends this on the wire?*
- **`pytest -s` masking a hang is a diagnostic clue, not noise** — the
  capture-on hang reproduced deterministically, the `-s` run passed;
  timing shifts from capture plumbing are enough to flip a race. Don't
  chase the pytest flags; find the race they perturb.
- Per-agent teardown bookkeeping (dicts keyed by agent name) replaced the
  flat subscription/source lists; shutdown order now stops gate watchers
  before the tasks/subscriptions they manage. Ordering rule: kill the
  thing that *creates* work before the things that *do* it.

## 2026-07-18 — Stage 3, run 9 (cloud executor): ADR-0056 wave 1

- **nats-server refuses to share the client port with the websocket
  listener** — `websocket { port: 4222 }` next to `port: 4222` is a fatal
  bind error at boot (verified on 2.10.24). ADR-0056's "share the standard
  mesh port" option never existed; defaults are now mesh port + 1 for the
  ws listener and 4224 for `oam ui`. Shaping check that caught it: boot the
  config you're about to promise, before writing it into an ADR.
- **`nats.ws` is deprecated on npm.** The JS ecosystem moved to
  `@nats-io/nats-core` (+ `jetstream`, `kv`) — which sdk-ts already uses.
  Discovered by probing the install, not by reading the ADR.
- **The TS SDK was already browser-ready and nobody noticed.** It selects
  `wsconnect` for ws:// URLs, keeps `transport-node` behind a dynamic
  import, and its `configUrl` connect option implements exactly the
  `/config.json` bootstrap ADR-0056 describes. Wave 2's browser client is
  therefore `@openagentmesh/sdk` via a workspace link — not a
  reimplementation of call/stream/catalog-watch. Check what an existing
  artifact already does before designing its replacement.
- **pnpm works in the cloud sandbox** via `corepack pnpm@10` (node 22 +
  corepack preinstalled; npm registry reachable through the proxy —
  installs resolve in under a second). No Go-proxy-style workaround needed.
- **ruff B008 exempts `typer.Option` defaults only for immutable-annotated
  parameters** (str/int/bool). A `Path`-annotated option trips it; the
  CLI-wide convention is str options converted inside the function.
- **ty flags `RequestHandlerClass(..., directory=...)`** because the
  attribute is typed against the base handler; instantiate the concrete
  handler class directly in `finish_request` instead of going through
  `RequestHandlerClass`.

## 2026-07-19 — Stage 3, run 10 (cloud executor): ADR-0056 wave 2

- **An unquoted `:` inside a GitHub Actions step name is fatal to the whole
  workflow** — `name: Build the SDK (link: target of ui/)` made the YAML
  unparseable, the run reports conclusion=failure with **zero jobs**, and
  `get_job_logs` has nothing to show. "Failure with 0 jobs" = workflow parse
  error; validate ci.yml with a YAML load locally before pushing.
- **`pkill -f <pattern>` can kill the shell running it** when the wrapper
  command line itself contains the pattern (the sandbox shell embeds the
  whole command in its argv). Symptom: exit code 144 and later chained
  commands never ran. Match on something not present in your own command
  line, or use pgrep first.
- **The `link:` protocol beats a pnpm workspace here**: a root
  pnpm-workspace.yaml would have moved sdk-ts's lockfile/install root and
  broken the existing sdk-ts CI job. `"@openagentmesh/sdk": "link:../sdk-ts"`
  keeps both packages standalone; the only cost is building the SDK
  (tsc → dist/) before ui typecheck/build — encoded as the first step of
  the ui CI job.
- **Injecting a fake client via React context beats vi.mock for SDK-consuming
  components**: `<MeshProvider client={fakeMesh()}>` keeps tests
  transport-free and type-checked against the real `MeshClient` interface —
  no module-mock drift when the SDK surface changes.
- **pnpm 10 blocks dependency build scripts by default** (esbuild's
  postinstall was skipped with only a warning). Declare
  `pnpm.onlyBuiltDependencies: ["esbuild"]` in package.json so local and CI
  installs behave identically instead of relying on the optional-dep binary
  path happening to exist.
- **The preinstalled Playwright chromium makes real-browser e2e cheap in the
  sandbox**: `npm i playwright` (module only, no browser download) +
  `executablePath: /opt/pw-browsers/chromium` drove the production UI against
  a real `oam mesh up` in one run — caught nothing this time, but it's the
  wave-5 smoke-test pattern, proven early.
- **jsdom + wsconnect never actually connect** — all UI tests go through the
  injected fake; the real websocket path is covered only by the browser e2e.
  Wave 5's Playwright test is therefore not optional polish; it is the only
  automated coverage of connect/config.json/KV-watch in the UI.

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

## 2026-07-18 — Stage 3, run 7 (cloud executor): ADR-0048 observability v1

- **The ADR's own aggregation wildcard was invalid NATS.** ADR-0048 hung logs
  off the agent subject (`mesh.agent.{name}.logs`) and claimed
  `mesh.agent.>.logs` for aggregation — but `>` only matches at the *end* of
  a subject. The sibling placement defeated the one property it was chosen
  for. Dedicated roots (`mesh.logs.{name}`, like `mesh.errors.`/`mesh.death.`)
  are the pattern that composes; check every proposed subject family's
  wildcard story against NATS matching rules at shaping time.
- **Shaping caught three stale claims before any code:** the ADR's context
  said heartbeats exist (deferred in ADR-0016 v1 — so "metrics in
  heartbeats" had nothing to ride on), used pre-ADR-0049 `{channel}.{name}`
  naming, and proposed a constructor-level observe config that would have
  raced the KV control plane (dropped: one control plane, no ambiguity).
  Discussion-status ADRs rot fastest; re-verify their premises against the
  repo at shaping time, not implementation time.
- **Lazy registration bit the tests again** (same trap as Stage 1's
  gateway): `agent_registered` fires on the first mesh operation after
  decoration, so log-subject taps see it interleaved with request events.
  Tests that tap a shared subject must filter by event type, never index
  positionally. Related nats-py footgun: `subscribe(cb=queue.put_nowait)`
  fails ("must use coroutine") — wrap in an async closure.
- **Default-level-zero-cost is a design property worth engineering for:**
  per-request events at `debug` + default `info` means steady-state adds no
  publishes at all, which dissolved the ADR's open perf question without
  benchmarks. Gate-before-build beats measure-after-build when the default
  can be "off".
- **Role templates moved in the same commit as the new bucket/subjects**
  (the run-5/run-6 lesson, applied): `$KV.mesh-observability.>` into the
  shared bucket list, `mesh.logs.>` + config-bucket read for observers.
  The 28 auth e2e tests passed unchanged on the first full-suite run.
- Two pre-existing docs gaps found while writing the reference updates:
  `subjects.md` never listed `mesh.death`/`mesh-instances` (liveness merge
  missed it), and the cookbook index table was missing three shipped
  recipes. Reference tables that duplicate nav structure drift silently;
  a docs-consistency sweep is a cheap future run item.
