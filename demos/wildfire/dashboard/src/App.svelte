<script lang="ts">
  // Placeholder root component. Plan 02-07 replaces this with the canvas
  // grid + click-to-spawn-fire UI wired to the dashboard WebSocket bridge.
  let status = $state("loading");
</script>

<main>
  <h1>Wildfire scenario UI</h1>
  <p>{status}...</p>
</main>

<style>
  main {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 0.5rem;
  }
  h1 {
    margin: 0;
    font-size: 1.5rem;
  }
  p {
    margin: 0;
    opacity: 0.7;
  }
</style>
