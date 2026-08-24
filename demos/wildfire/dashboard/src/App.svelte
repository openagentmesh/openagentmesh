<script lang="ts">
  // Wildfire scenario UI: mission-control shell around the tactical canvas.
  //
  // Layout: top command bar (identity, swarm stats, connection), full-bleed
  // canvas stage, right intel column (incident briefing / mission log /
  // narrator). Fleet sprites are clickable: popover with unit telemetry and
  // the Phase 4 chaos-kill action. Ground clicks cycle fire magnitude
  // (off -> 200 -> 500 -> 800°C) per D-49/D-53.

  import { onMount, onDestroy } from "svelte";
  import { get } from "svelte/store";
  import {
    cellsStore,
    fleetStore,
    detectionsStore,
    connectionStore,
    briefingsStore,
    latestBriefingStore,
    narrativeStore,
    statsStore,
    eventsStore,
    openMeshWebSocket,
    sendClick,
    sendChaosKill,
    type FleetMember,
  } from "./lib/mesh";
  import { Renderer } from "./lib/canvas";
  import { advance } from "./lib/magnitude";
  import { pixelToKm } from "./lib/coords";

  let canvas: HTMLCanvasElement | undefined = $state();
  let renderer: Renderer | null = null;
  let closeWs: (() => void) | null = null;

  let selected: FleetMember | null = $state(null);
  let popoverAt: { x: number; y: number } | null = $state(null);
  let clock = $state(new Date());
  let clockTimer: ReturnType<typeof setInterval> | null = null;

  function fitCanvas(): void {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
  }

  function canvasPixel(e: MouseEvent): { px: number; py: number } {
    const rect = canvas!.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    return {
      px: (e.clientX - rect.left) * dpr,
      py: (e.clientY - rect.top) * dpr,
    };
  }

  function handleClick(e: MouseEvent): void {
    if (!canvas || !renderer) return;
    const { px, py } = canvasPixel(e);

    const hit = renderer.hitTest(px, py);
    if (hit) {
      selected = hit;
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const anchor = renderer.spritePixel(hit.instance_id);
      popoverAt = anchor
        ? { x: rect.left + anchor.px / dpr, y: rect.top + anchor.py / dpr }
        : { x: e.clientX, y: e.clientY };
      return;
    }
    if (selected) {
      // First ground click just dismisses the popover.
      selected = null;
      popoverAt = null;
      return;
    }
    const { x, y } = pixelToKm(px, py, canvas.width, canvas.height);
    const { temperature } = advance(x, y);
    sendClick({ x, y }, temperature);
  }

  function killSelected(): void {
    if (!selected) return;
    sendChaosKill(selected.instance_id);
    selected = null;
    popoverAt = null;
  }

  function handleKeydown(e: KeyboardEvent): void {
    if (e.key === "Escape") {
      selected = null;
      popoverAt = null;
    }
  }

  onMount(() => {
    fitCanvas();
    window.addEventListener("resize", fitCanvas);
    window.addEventListener("keydown", handleKeydown);
    // Terrain seed comes from the server (WILDFIRE_SEED) so the recording
    // is reproducible; fall back to 42 if /health is unreachable.
    (async () => {
      let seed = 42;
      try {
        const res = await fetch("/health");
        const body = (await res.json()) as { seed?: number };
        if (typeof body.seed === "number") seed = body.seed;
      } catch {
        // keep default
      }
      if (canvas) {
        renderer = new Renderer(
          canvas,
          () => ({
            cells: get(cellsStore),
            fleet: get(fleetStore),
            detections: get(detectionsStore),
            selectedId: selected?.instance_id ?? null,
          }),
          seed,
        );
        renderer.start();
      }
    })();
    closeWs = openMeshWebSocket();
    clockTimer = setInterval(() => (clock = new Date()), 1000);
  });

  onDestroy(() => {
    renderer?.stop();
    closeWs?.();
    window.removeEventListener("resize", fitCanvas);
    window.removeEventListener("keydown", handleKeydown);
    if (clockTimer) clearInterval(clockTimer);
  });

  const sevColor: Record<string, string> = {
    low: "var(--ember-400)",
    med: "var(--ember-500)",
    high: "var(--ember-600)",
    critical: "var(--ember-700)",
  };

  let briefing = $derived($latestBriefingStore);
  let stats = $derived($statsStore);
  let narrative = $derived($narrativeStore);
  let events = $derived($eventsStore);
  let hasDetections = $derived($detectionsStore.size > 0);
  let hasBriefings = $derived($briefingsStore.size > 0);
  let conn = $derived($connectionStore);

  function hhmmss(tsMs: number): string {
    return new Date(tsMs).toLocaleTimeString("en-GB");
  }
</script>

<main>
  <header class="topbar">
    <div class="brand">
      <span class="brand-name">WILDFIRE RESPONSE MESH</span>
      <span class="brand-sub">OpenAgentMesh scenario</span>
    </div>
    {#if stats}
      <div class="stats-strip" aria-label="swarm-stats">
        <span class="stat"><em>UAV</em> {stats.uavs_active}/{stats.uavs_total}</span>
        <span class="stat"><em>DRONE</em> {stats.drones_active}/{stats.drones_total}</span>
        <span class="stat"><em>HELI</em> {stats.helis_active}/{stats.helis_total}</span>
        <span class="stat"><em>FFUNIT</em> {stats.ffunits_active}/{stats.ffunits_total}</span>
        <span class="stat"><em>MEDEVAC</em> {stats.medevacs_active}/{stats.medevacs_total}</span>
        <span class="stat sep"><em>INCIDENTS</em> {stats.incidents_open} open</span>
        <span class="stat"><em>DETECTIONS</em> {stats.fires_detected_total}</span>
      </div>
    {:else}
      <div class="stats-strip muted">awaiting swarm stats…</div>
    {/if}
    <div class="top-right">
      <span class="clock">{clock.toLocaleTimeString("en-GB")}</span>
      <span class="conn conn-{conn}">
        <span class="conn-dot"></span>{conn}
      </span>
    </div>
  </header>

  <div class="body">
    <div class="stage">
      <canvas bind:this={canvas} onclick={handleClick}></canvas>
      <div class="stage-hint">click terrain to ignite · click again to intensify · click a unit for actions</div>
    </div>

    <aside class="intel">
      <section class="pane briefing-pane">
        <h2 class="pane-title">Incident briefing <span class="agent-tag">briefer</span></h2>
        {#if briefing}
          {#key briefing.issued_at}
            <div class="briefing card-in">
              <div class="briefing-head">
                <span class="sev-chip" style="--sev: {sevColor[briefing.severity]}">{briefing.severity}</span>
                <span class="mono dim">{briefing.incident_id}</span>
                <span class="mono dim right">{hhmmss(briefing.issued_at * 1000)}</span>
              </div>
              <p class="briefing-summary">{briefing.summary}</p>
              <div class="briefing-grid">
                <span class="k">persons</span><span class="v mono">{briefing.persons_estimated}</span>
                <span class="k">structures</span><span class="v mono">{briefing.structures_at_risk}</span>
                <span class="k">confidence</span><span class="v mono">{(briefing.confidence * 100).toFixed(0)}%</span>
                <span class="k">sources</span><span class="v mono">{briefing.sources.length} detection{briefing.sources.length === 1 ? "" : "s"}</span>
              </div>
              {#if briefing.recommended_actions.length}
                <div class="actions">
                  {#each briefing.recommended_actions as a (a)}
                    <span class="action-chip">{a.replace("dispatch_", "→ ")}</span>
                  {/each}
                </div>
              {/if}
            </div>
          {/key}
        {:else if hasDetections}
          <div class="thinking">
            <span class="thinking-dot"></span>
            <div class="thinking-body">
              <p class="thinking-line"><span class="mono">briefer</span> is correlating detections…</p>
              <div class="skeleton"></div>
              <div class="skeleton w60"></div>
            </div>
          </div>
        {:else}
          <p class="empty">No active incident. Ignite terrain to start the cascade.</p>
        {/if}
      </section>

      <section class="pane log-pane">
        <h2 class="pane-title">Mission log</h2>
        {#if events.length === 0}
          <p class="empty">Quiet. The mesh is listening.</p>
        {:else}
          <ul class="log">
            {#each events as ev (ev.t + ev.text)}
              <li class="log-row tone-{ev.tone}">
                <span class="log-time mono">{hhmmss(ev.t)}</span>
                <span class="log-text mono">{ev.text}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </section>

      <section class="pane narrative-pane">
        <h2 class="pane-title">Situation narrative <span class="agent-tag">narrator</span></h2>
        {#if narrative}
          <p class="narrative card-in">{narrative.text}</p>
        {:else if hasBriefings}
          <p class="empty">First narrative summary arrives on the narrator's next 5-minute pass.</p>
        {:else}
          <p class="empty">The narrator reports every 5 minutes once the mesh has a story to tell.</p>
        {/if}
      </section>
    </aside>
  </div>

  {#if selected && popoverAt}
    <div class="popover" style="left: {popoverAt.x}px; top: {popoverAt.y}px">
      <div class="popover-head">
        <span class="popover-type">{selected.zone}.{selected.fleet_type}</span>
        <span class="mono dim">{selected.instance_id.slice(0, 12)}</span>
      </div>
      <div class="popover-grid">
        <span class="k">state</span><span class="v mono">{selected.state}</span>
        <span class="k">assignment</span><span class="v mono">{selected.current_assignment ?? "—"}</span>
        {#if selected.coords}
          <span class="k">position</span>
          <span class="v mono">{selected.coords.x.toFixed(2)}, {selected.coords.y.toFixed(2)} km</span>
        {/if}
      </div>
      <button class="kill-btn" onclick={killSelected}>Kill process</button>
      <p class="kill-hint">Publishes mesh.chaos.kill — the process dies uncleanly.</p>
    </div>
  {/if}
</main>

<style>
  :global(:root) {
    --ink-950: #0a0d11;
    --ink-900: #0f1319;
    --ink-850: #141a22;
    --ink-800: #1a212b;
    --ink-700: #232c38;
    --ink-600: #2e3947;
    --ink-500: #3d4a5c;
    --ink-400: #5b6b80;
    --ink-300: #8494a9;
    --ink-200: #aab8c9;
    --ink-100: #d6dee8;
    --ink-50: #eef2f7;
    --ember-300: #ffd08a;
    --ember-400: #ffb74a;
    --ember-500: #ff8a3d;
    --ember-600: #f4511e;
    --ember-700: #d32f2f;
    --live: #3fb950;
    --dead: #f85149;
    --stale: #d29922;
    --mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  }

  main {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: var(--ink-950);
    color: var(--ink-100);
    font-family: var(--sans);
    font-size: 13px;
    overflow: hidden;
  }

  .mono { font-family: var(--mono); }
  .dim { color: var(--ink-400); font-size: 11px; }
  .right { margin-left: auto; }

  /* ---- top bar ---- */
  .topbar {
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 8px 16px;
    background: var(--ink-900);
    border-bottom: 1px solid var(--ink-700);
    flex: 0 0 auto;
  }
  .brand { display: flex; flex-direction: column; line-height: 1.2; }
  .brand-name {
    font-weight: 650;
    letter-spacing: 0.08em;
    font-size: 13px;
    color: var(--ink-50);
  }
  .brand-sub {
    font-size: 10px;
    color: var(--ink-400);
    letter-spacing: 0.04em;
  }
  .stats-strip {
    display: flex;
    gap: 14px;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink-100);
    flex: 1;
    justify-content: center;
  }
  .stats-strip.muted { color: var(--ink-500); }
  .stat em {
    font-style: normal;
    color: var(--ink-400);
    font-size: 9px;
    letter-spacing: 0.1em;
    margin-right: 4px;
  }
  .stat.sep { border-left: 1px solid var(--ink-700); padding-left: 14px; }
  .top-right { display: flex; align-items: center; gap: 12px; }
  .clock { font-family: var(--mono); font-size: 12px; color: var(--ink-200); }
  .conn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink-300);
  }
  .conn-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--stale); }
  .conn-connected .conn-dot { background: var(--live); }
  .conn-disconnected .conn-dot,
  .conn-reconnecting .conn-dot { background: var(--dead); animation: pulse 1.2s infinite; }

  /* ---- body: stage + intel ---- */
  .body { display: flex; flex: 1; min-height: 0; }
  .stage { position: relative; flex: 1; min-width: 0; }
  canvas {
    width: 100%;
    height: 100%;
    display: block;
    cursor: crosshair;
    background: var(--ink-950);
  }
  .stage-hint {
    position: absolute;
    left: 12px;
    bottom: 10px;
    font-family: var(--mono);
    font-size: 10px;
    color: rgba(170, 190, 210, 0.4);
    letter-spacing: 0.03em;
    pointer-events: none;
  }

  .intel {
    width: 360px;
    flex: 0 0 360px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 10px;
    background: var(--ink-950);
    border-left: 1px solid var(--ink-700);
    min-height: 0;
    overflow: hidden;
  }
  .pane {
    background: var(--ink-900);
    border: 1px solid var(--ink-700);
    border-radius: 6px;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .briefing-pane { flex: 0 0 auto; }
  .log-pane { flex: 1 1 auto; min-height: 80px; }
  .narrative-pane { flex: 0 0 auto; max-height: 180px; }
  .pane-title {
    margin: 0 0 8px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--ink-400);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .agent-tag {
    font-family: var(--mono);
    font-size: 9px;
    text-transform: none;
    letter-spacing: 0.02em;
    color: var(--ink-300);
    background: var(--ink-800);
    border-radius: 3px;
    padding: 1px 5px;
  }
  .empty { color: var(--ink-500); font-size: 12px; margin: 2px 0; line-height: 1.5; }

  /* briefing card */
  .briefing-head { display: flex; align-items: center; gap: 8px; }
  .sev-chip {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--ink-950);
    background: var(--sev);
    border-radius: 3px;
    padding: 2px 7px;
  }
  .briefing-summary {
    margin: 8px 0;
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--ink-100);
  }
  .briefing-grid, .popover-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px 12px;
    font-size: 11px;
  }
  .k { color: var(--ink-400); }
  .v { color: var(--ink-100); }
  .actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .action-chip {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--ember-300);
    border: 1px solid rgba(255, 183, 74, 0.35);
    border-radius: 3px;
    padding: 2px 6px;
  }

  /* thinking / skeleton state */
  .thinking { display: flex; gap: 10px; align-items: flex-start; padding: 2px 0; }
  .thinking-body { flex: 1; }
  .thinking-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--ember-400);
    margin-top: 4px;
    animation: pulse 1.2s ease-in-out infinite;
    flex: 0 0 auto;
  }
  .thinking-line { margin: 0 0 8px; font-size: 12px; color: var(--ink-200); }
  .skeleton {
    height: 9px;
    border-radius: 3px;
    background: linear-gradient(90deg, var(--ink-800) 25%, var(--ink-700) 50%, var(--ink-800) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.4s infinite;
    margin-bottom: 6px;
    width: 100%;
  }
  .skeleton.w60 { width: 60%; }

  /* mission log */
  .log {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }
  .log-row {
    display: flex;
    gap: 10px;
    padding: 3px 0;
    border-bottom: 1px solid var(--ink-850);
    animation: slide-in 240ms cubic-bezier(0.2, 0.7, 0.3, 1);
  }
  .log-time { color: var(--ink-500); font-size: 10px; flex: 0 0 auto; padding-top: 1px; }
  .log-text { font-size: 11px; color: var(--ink-200); word-break: break-word; }
  .tone-ember .log-text { color: var(--ember-400); }
  .tone-amber .log-text { color: var(--ember-300); }
  .tone-alarm .log-text { color: var(--dead); }
  .tone-ok .log-text { color: var(--live); }

  /* narrative */
  .narrative {
    margin: 0;
    font-size: 12px;
    line-height: 1.6;
    color: var(--ink-200);
    overflow-y: auto;
  }

  /* popover */
  .popover {
    position: fixed;
    transform: translate(14px, -50%);
    background: var(--ink-850);
    border: 1px solid var(--ink-600);
    border-radius: 6px;
    padding: 10px 12px;
    width: 230px;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.55);
    z-index: 20;
    animation: pop-in 180ms cubic-bezier(0.2, 0.7, 0.3, 1);
  }
  .popover-head { display: flex; flex-direction: column; margin-bottom: 8px; }
  .popover-type { font-family: var(--mono); font-size: 12px; font-weight: 600; color: var(--ink-50); }
  .kill-btn {
    margin-top: 10px;
    width: 100%;
    background: transparent;
    color: var(--dead);
    border: 1px solid rgba(248, 81, 73, 0.5);
    border-radius: 4px;
    font-family: var(--mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 6px 0;
    cursor: pointer;
    transition: background 160ms, color 160ms;
  }
  .kill-btn:hover { background: var(--dead); color: var(--ink-950); }
  .kill-hint { margin: 6px 0 0; font-size: 9.5px; color: var(--ink-500); line-height: 1.4; }

  /* card entrance */
  .card-in { animation: slide-in 300ms cubic-bezier(0.2, 0.7, 0.3, 1); }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }
  @keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
  @keyframes slide-in {
    from { opacity: 0; transform: translateY(-6px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes pop-in {
    from { opacity: 0; transform: translate(14px, -50%) scale(0.96); }
    to { opacity: 1; transform: translate(14px, -50%) scale(1); }
  }
</style>
