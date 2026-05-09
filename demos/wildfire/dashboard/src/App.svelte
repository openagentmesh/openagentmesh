<script lang="ts">
  // Wildfire scenario UI root component (plan 02-07).
  //
  // Mounts a full-window canvas, opens the WebSocket to the dashboard
  // backend, runs the Renderer loop, and translates canvas clicks into
  // {type: "click", coords, temperature} frames per D-49 / D-53.

  import { onMount, onDestroy } from "svelte";
  import { get } from "svelte/store";
  import {
    cellsStore,
    fleetStore,
    detectionsStore,
    connectionStore,
    openMeshWebSocket,
    sendClick,
  } from "./lib/mesh";
  import { Renderer } from "./lib/canvas";
  import { advance } from "./lib/magnitude";
  import { pixelToKm } from "./lib/coords";

  let canvas: HTMLCanvasElement | undefined = $state();
  let renderer: Renderer | null = null;
  let closeWs: (() => void) | null = null;

  function fitCanvas(): void {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
  }

  function handleClick(e: MouseEvent): void {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const px = (e.clientX - rect.left) * dpr;
    const py = (e.clientY - rect.top) * dpr;
    const { x, y } = pixelToKm(px, py, canvas.width, canvas.height);
    const { temperature } = advance(x, y);
    sendClick({ x, y }, temperature);
  }

  onMount(() => {
    fitCanvas();
    window.addEventListener("resize", fitCanvas);
    if (canvas) {
      renderer = new Renderer(canvas, () => ({
        cells: get(cellsStore),
        fleet: get(fleetStore),
        detections: get(detectionsStore),
      }));
      renderer.start();
    }
    closeWs = openMeshWebSocket();
  });

  onDestroy(() => {
    renderer?.stop();
    closeWs?.();
    window.removeEventListener("resize", fitCanvas);
  });
</script>

<main>
  <header>
    <h1>Wildfire scenario UI</h1>
    <span class="status status-{$connectionStore}">{$connectionStore}</span>
  </header>
  <canvas bind:this={canvas} on:click={handleClick}></canvas>
</main>

<style>
  main {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  header {
    padding: 0.5rem 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #111;
    color: #eee;
  }
  header h1 {
    font-size: 1rem;
    margin: 0;
  }
  .status {
    font-size: 0.875rem;
    padding: 0.125rem 0.5rem;
    border-radius: 999px;
    background: #333;
  }
  .status-connected {
    background: #064;
  }
  .status-reconnecting,
  .status-connecting {
    background: #640;
  }
  .status-disconnected {
    background: #600;
  }
  canvas {
    flex: 1;
    width: 100%;
    cursor: crosshair;
    background: #f4f1ea;
    display: block;
  }
</style>
