"""fire-sim: ``kv_source`` Watcher + 1 Hz internal spread tick.

Per ``.planning/phases/01-detection-foundation/01-CONTEXT.md`` Amendment A-04
fire-sim is a Watcher on the world-cell KV namespace, NOT a publisher.

Shape (per A-04 + A-08):

- One ``@mesh.agent`` registration whose handler is annotated
  ``async def fire_sim(entry: KVEntry[CellState]) -> None`` and bound to
  ``mesh.kv_source("wildfire.world.cell.*", on_init="replay")``.
- A separate asyncio task (``_spread_loop``) ticks every
  ``FIRE_SIM_TICK_INTERVAL_S`` seconds, runs the in-process spread CA over
  the 50x50 grid, and writes only cells whose temperature shifted by at
  least ``FIRE_SIM_MATERIAL_DELTA_C`` back to KV via ``mesh.kv.put_model``.
- Cells decaying back to ambient are deleted via ``mesh.kv.delete``
  (sparse-KV invariant per A-03: ambient = absence of a key).
- Self-write filter (A-04): every payload carries
  ``last_modified_by = mesh.instance_id``; the kv_source handler skips
  entries whose value's ``last_modified_by`` matches the agent's own
  instance id, breaking the read-your-write feedback loop.
- Boot snapshot replay: ``on_init="replay"`` (the default) re-fires every
  existing ``wildfire.world.cell.*`` entry on agent start so the
  in-process grid rebuilds from KV state on a restart.

Anti-scope (per A-04 + A-08): this module ships zero pubsub surface. The
old pre-amendment thermal-grid publisher and the spawn / suppress
subscriber surfaces are gone; KV is the only data plane.

Boot UX::

    python -m demos.wildfire.world.fire_sim

Reads ``NATS_URL`` (default ``nats://127.0.0.1:4222``); the orchestrator
in ``demos/wildfire/__main__.py`` exports it for child processes.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import time

from demos.wildfire.core.config import (
    FIRE_SIM_AMBIENT_C,
    FIRE_SIM_DECAY_PER_TICK_C,
    FIRE_SIM_MATERIAL_DELTA_C,
    FIRE_SIM_MAX_C,
    FIRE_SIM_SPREAD_DIFFUSION,
    FIRE_SIM_TICK_INTERVAL_S,
)
from demos.wildfire.core.contracts import CellState
from demos.wildfire.core.keys import (
    CELL_PREFIX,
    GRID_DIM,
    cell_center,
    cell_key,
)
from openagentmesh import AgentMesh, AgentSpec, KVEntry

_log = logging.getLogger("wildfire.fire_sim")


class FireSim:
    """In-process world grid + spread model.

    Decoupled from the SDK so unit tests (``tests/wildfire/unit/test_fire_sim.py``)
    can exercise the spread arithmetic without booting NATS.
    """

    def __init__(self) -> None:
        # Sparse: dict[(x_idx, y_idx)] -> temperature_c. Cells absent from
        # this dict are at ambient (FIRE_SIM_AMBIENT_C) by convention (A-03).
        self._grid: dict[tuple[int, int], float] = {}

    # --- External-mutation entry points (called by the kv_source handler) ---

    def integrate_cell(self, x_idx: int, y_idx: int, temperature: float) -> None:
        """Set the temperature of a cell from an external KV write."""
        self._grid[(x_idx, y_idx)] = temperature

    def drop_cell(self, x_idx: int, y_idx: int) -> None:
        """Remove a cell (DELETE op from KV, or post-tick decay to ambient)."""
        self._grid.pop((x_idx, y_idx), None)

    # --- Internal tick ---

    def tick(
        self,
    ) -> tuple[dict[tuple[int, int], float], list[tuple[int, int]]]:
        """Run one spread tick.

        Returns ``(cells_changed, cells_to_delete)`` so the wrapping
        ``_spread_loop`` issues one ``mesh.kv.put_model`` per changed cell
        and one ``mesh.kv.delete`` per decayed-to-ambient cell.

        Algorithm (toy CA, tunable):

        1. Each currently hot cell self-decays by ``FIRE_SIM_DECAY_PER_TICK_C``
           and absorbs ``FIRE_SIM_SPREAD_DIFFUSION * mean(positive neighbour
           excess)`` from its 4-neighbours, capped at ``FIRE_SIM_MAX_C``.
        2. Cold neighbours of any hot cell pick up
           ``FIRE_SIM_SPREAD_DIFFUSION * (hot_cell_temp - FIRE_SIM_AMBIENT_C)``
           bleed; if that exceeds ``FIRE_SIM_MATERIAL_DELTA_C`` the neighbour
           ignites at ``FIRE_SIM_AMBIENT_C + bleed``.
        3. Cells whose post-tick temperature falls at or below
           ``FIRE_SIM_AMBIENT_C`` go to the deletion queue (sparse invariant);
           cells whose change is below ``FIRE_SIM_MATERIAL_DELTA_C`` stay in
           the in-process grid but are NOT written to KV (noise filter).
        """
        new_grid: dict[tuple[int, int], float] = {}
        cells_changed: dict[tuple[int, int], float] = {}
        cells_to_delete: list[tuple[int, int]] = []

        # 1. Self-decay + neighbour-absorption for already-hot cells.
        for (x, y), temp in self._grid.items():
            new_temp = temp - FIRE_SIM_DECAY_PER_TICK_C

            excess = 0.0
            n = 0
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < GRID_DIM and 0 <= ny < GRID_DIM:
                    n_temp = self._grid.get((nx, ny), FIRE_SIM_AMBIENT_C)
                    if n_temp > temp:
                        excess += n_temp - temp
                    n += 1
            if n:
                new_temp += FIRE_SIM_SPREAD_DIFFUSION * (excess / n)

            if new_temp > FIRE_SIM_MAX_C:
                new_temp = FIRE_SIM_MAX_C

            if new_temp > FIRE_SIM_AMBIENT_C:
                new_grid[(x, y)] = new_temp
                if abs(new_temp - temp) >= FIRE_SIM_MATERIAL_DELTA_C:
                    cells_changed[(x, y)] = new_temp
            else:
                cells_to_delete.append((x, y))

        # 2. Ignite cold neighbours of any hot cell whose bleed exceeds
        #    the material-write threshold. Iterate over the original grid
        #    so ignitions this tick don't cascade synchronously (one CA step).
        for (x, y), temp in self._grid.items():
            if temp <= FIRE_SIM_AMBIENT_C:
                continue
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if not (0 <= nx < GRID_DIM and 0 <= ny < GRID_DIM):
                    continue
                if (nx, ny) in self._grid:
                    continue  # neighbour already hot, handled in pass 1
                bleed = FIRE_SIM_SPREAD_DIFFUSION * (temp - FIRE_SIM_AMBIENT_C)
                if bleed < FIRE_SIM_MATERIAL_DELTA_C:
                    continue
                ignited_temp = FIRE_SIM_AMBIENT_C + bleed
                if ignited_temp > FIRE_SIM_MAX_C:
                    ignited_temp = FIRE_SIM_MAX_C
                # If two neighbours both try to ignite (nx, ny), keep the hotter.
                if (
                    (nx, ny) not in cells_changed
                    or cells_changed[(nx, ny)] < ignited_temp
                ):
                    cells_changed[(nx, ny)] = ignited_temp
                if (nx, ny) not in new_grid or new_grid[(nx, ny)] < ignited_temp:
                    new_grid[(nx, ny)] = ignited_temp

        self._grid = new_grid
        return cells_changed, cells_to_delete


# ---------------------------------------------------------------------------
# Agent registration + spread-tick task
# ---------------------------------------------------------------------------


def _parse_cell_key(key: str) -> tuple[int, int] | None:
    """Parse ``wildfire.world.cell.<x>.<y>`` -> ``(x_idx, y_idx)`` or None.

    Defensive against malformed keys per threat T-01-04-02 (Tampering): a
    bad key is logged at the call site and the handler returns without
    crashing the agent.
    """
    if not key.startswith(CELL_PREFIX + "."):
        return None
    tail = key[len(CELL_PREFIX) + 1 :]
    parts = tail.split(".")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def build_agent(mesh: AgentMesh, sim: FireSim) -> None:
    """Register the fire-sim agent on ``mesh`` against the shared ``sim`` grid.

    Split out so unit / integration tests can register the handler against
    an ``AgentMesh.local()`` fixture without going through the ``__main__``
    boot path.
    """

    @mesh.agent(
        AgentSpec(
            name="fire-sim",
            description=(
                "Wildfire spread simulator: 50x50 in-process thermal grid driven "
                "by KV writes on wildfire.world.cell.*; runs a 1 Hz spread tick "
                "and writes only changed cells back via the same KV namespace."
            ),
        ),
        sources=[mesh.kv_source(f"{CELL_PREFIX}.*", on_init="replay")],
    )
    async def fire_sim(entry: KVEntry[CellState]) -> None:
        # DELETE op: drop the cell from the in-process grid; nothing else to
        # do (the writer already removed it from KV; no risk of a feedback
        # loop because we don't re-write on DELETE).
        if entry.operation == "DELETE":
            parsed = _parse_cell_key(entry.key)
            if parsed is None:
                _log.warning("malformed cell key on DELETE: %r", entry.key)
                return
            sim.drop_cell(*parsed)
            return

        # PUT op: integrate the external write into the in-process grid,
        # but only if it's not our own delta (A-04 self-write filter).
        if entry.value.last_modified_by == mesh.instance_id:
            return

        parsed = _parse_cell_key(entry.key)
        if parsed is None:
            _log.warning("malformed cell key on PUT: %r", entry.key)
            return
        sim.integrate_cell(*parsed, entry.value.temperature)


async def _spread_loop(mesh: AgentMesh, sim: FireSim) -> None:
    """Tick the in-process grid every ``FIRE_SIM_TICK_INTERVAL_S`` seconds.

    Writes only materially-changed cells back to KV; deletes cells decaying
    to ambient (sparse-KV invariant). Each write carries
    ``last_modified_by = mesh.instance_id`` so the kv_source handler's
    self-write filter (A-04) skips them.
    """
    try:
        while True:
            await asyncio.sleep(FIRE_SIM_TICK_INTERVAL_S)
            try:
                changed, deleted = sim.tick()
            except Exception as e:  # pragma: no cover -- defensive guard
                _log.warning("spread tick failed: %s", e)
                continue

            for (x_idx, y_idx), temp in changed.items():
                center = cell_center(x_idx, y_idx)
                state = CellState(
                    coords=center,
                    temperature=temp,
                    last_modified_at=time.time(),
                    last_modified_by=mesh.instance_id,
                )
                try:
                    await mesh.kv.put_model(cell_key(center.x, center.y), state)
                except Exception as e:
                    _log.warning(
                        "put_model failed for cell (%d,%d): %s", x_idx, y_idx, e
                    )

            for x_idx, y_idx in deleted:
                center = cell_center(x_idx, y_idx)
                try:
                    await mesh.kv.delete(cell_key(center.x, center.y))
                except Exception as e:
                    _log.warning(
                        "delete failed for cell (%d,%d): %s", x_idx, y_idx, e
                    )
    except asyncio.CancelledError:
        return


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    sim = FireSim()
    build_agent(mesh, sim)

    # Wire SIGTERM to a clean-shutdown event so the orchestrator's
    # ``Popen.terminate()`` (SIGTERM) on shutdown unblocks ``stop_event``
    # the same way Ctrl-C does. SIGINT is delivered as KeyboardInterrupt
    # by the asyncio default handler; we mirror it as a stop-event signal.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # Windows + some non-main-thread contexts don't support
        # add_signal_handler; the KeyboardInterrupt fallback below covers SIGINT.
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop_event.set)

    async with mesh:
        tick_task = asyncio.create_task(_spread_loop(mesh, sim))
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            tick_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tick_task


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
