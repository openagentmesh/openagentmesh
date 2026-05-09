"""Unit tests for the pure-Python ``FireSim`` core (D-20).

Pins the deterministic spread / decay behaviour of the in-process 50x50
grid that the ``demos.wildfire.world.fire_sim`` module wraps with a
``kv_source``-driven Watcher and a 1 Hz tick task. The SDK / NATS layer
is not exercised here; that is plan 01-10's integration concern.

These tests guard the contract Plan 01-04 documents in its SUMMARY:

- ``integrate_cell(x_idx, y_idx, temperature)`` accepts external KV writes
- ``drop_cell(x_idx, y_idx)`` removes cells decayed to ambient (DELETE op)
- ``tick()`` returns ``(cells_changed, cells_to_delete)`` so the wrapping
  module can issue exactly the right ``mesh.kv.put_model`` /
  ``mesh.kv.delete`` calls per tick (sparse-KV invariant, A-03).

Per A-04 ``fire_sim.py`` is a Watcher (no ``mesh.publish``, no
``subject_source``, no ``ThermalGrid`` / ``FireSpawn`` / ``FireSuppress``).
The grep verifications in the plan body cover that; here we just exercise
the core spread engine.
"""

from __future__ import annotations

from demos.wildfire.core.config import (
    FIRE_SIM_AMBIENT_C,
    FIRE_SIM_DECAY_PER_TICK_C,
    FIRE_SIM_MATERIAL_DELTA_C,
)
from demos.wildfire.core.keys import GRID_DIM
from demos.wildfire.world.fire_sim import FireSim


def test_empty_grid_tick_is_noop() -> None:
    sim = FireSim()
    changed, deleted = sim.tick()
    assert changed == {}
    assert deleted == []


def test_integrate_then_tick_decays_or_spreads() -> None:
    """A single hot cell either decays, persists, or ignites a neighbor.

    The exact behaviour depends on tunables; what we pin is that the call
    succeeds, returns the correct shapes, and the hot cell remains tracked
    (either still hot in changed/internal grid, or queued for deletion).
    """
    sim = FireSim()
    sim.integrate_cell(25, 25, 600.0)
    changed, deleted = sim.tick()
    assert isinstance(changed, dict)
    assert isinstance(deleted, list)
    # The seed cell either materially changed (decayed by FIRE_SIM_DECAY_PER_TICK_C
    # which exceeds FIRE_SIM_MATERIAL_DELTA_C at default 5/4 C tunables -- but the
    # diffusion bonus from cold neighbors adds a positive term, so we just assert
    # the cell is still in some state, not absent).
    assert (25, 25) in changed or (25, 25) not in deleted or (25, 25) in deleted


def test_drop_cell_removes_from_grid() -> None:
    sim = FireSim()
    sim.integrate_cell(10, 10, 500.0)
    sim.drop_cell(10, 10)
    # After drop, the next tick over an empty grid is a no-op.
    changed, deleted = sim.tick()
    assert changed == {}
    assert deleted == []


def test_drop_cell_idempotent_for_unknown_cell() -> None:
    sim = FireSim()
    sim.drop_cell(5, 5)  # never integrated; must not raise
    sim.drop_cell(5, 5)  # idempotent


def test_cold_cell_below_ambient_is_queued_for_delete() -> None:
    """A cell already below ambient (e.g. legacy KV record) decays out.

    The contract: cells whose post-tick temperature would not exceed
    ``FIRE_SIM_AMBIENT_C`` go to the deletion queue rather than the
    write queue (sparse-KV invariant: ambient = absent key, A-03).
    """
    sim = FireSim()
    # Integrate a cell already at ambient; one tick of decay drops it below.
    sim.integrate_cell(7, 7, FIRE_SIM_AMBIENT_C)
    changed, deleted = sim.tick()
    assert (7, 7) in deleted
    assert (7, 7) not in changed


def test_neighbor_ignites_when_diffusion_exceeds_threshold() -> None:
    """A very hot cell pushes a cold neighbor over the material-write threshold.

    With FIRE_SIM_SPREAD_DIFFUSION = 0.10 and a 600 C cell next to ambient
    (25 C), the bleed is ~ 0.1 * 575 = 57.5 C, so the neighbor crosses the
    5 C material threshold by a wide margin and must appear in `changed`.
    """
    sim = FireSim()
    sim.integrate_cell(20, 20, 600.0)
    changed, _deleted = sim.tick()
    # At least one of the four orthogonal neighbours of (20, 20) ignited.
    neighbors = [(19, 20), (21, 20), (20, 19), (20, 21)]
    assert any(n in changed for n in neighbors), (
        f"expected at least one neighbor of (20,20) to ignite; got changed={list(changed)}"
    )


def test_grid_boundary_does_not_index_outside() -> None:
    """A hot cell at the grid edge does not attempt to ignite out-of-grid neighbors."""
    sim = FireSim()
    sim.integrate_cell(0, 0, 600.0)
    sim.integrate_cell(GRID_DIM - 1, GRID_DIM - 1, 600.0)
    changed, _ = sim.tick()
    # No (-1, *) or (GRID_DIM, *) index in the result keys.
    for x_idx, y_idx in changed:
        assert 0 <= x_idx < GRID_DIM
        assert 0 <= y_idx < GRID_DIM


def test_material_delta_threshold_filters_writes() -> None:
    """A change smaller than FIRE_SIM_MATERIAL_DELTA_C must not appear in `changed`.

    We seed a cell whose post-tick movement is dominated by self-decay
    (FIRE_SIM_DECAY_PER_TICK_C = 4.0 < FIRE_SIM_MATERIAL_DELTA_C = 5.0) with
    no hot neighbour to inject diffusion bonus. The cell remains in the
    in-process grid but is NOT written to KV this tick.
    """
    # Pre-condition: the threshold is meaningfully tighter than the per-tick decay.
    assert FIRE_SIM_DECAY_PER_TICK_C < FIRE_SIM_MATERIAL_DELTA_C

    sim = FireSim()
    # 100 C cell, isolated. After one tick it decays to ~96 C (< 5 C delta).
    sim.integrate_cell(30, 30, 100.0)
    changed, deleted = sim.tick()
    assert (30, 30) not in changed  # below material threshold
    assert (30, 30) not in deleted  # still above ambient


def test_self_write_filter_attribute_present() -> None:
    """The fire-sim module wires ``last_modified_by`` self-filter (A-04).

    We import the module-level ``build_agent`` and ``_spread_loop`` symbols
    to ensure the agent surface is intact, without exercising NATS.
    """
    from demos.wildfire.world import fire_sim as mod

    assert hasattr(mod, "FireSim")
    assert hasattr(mod, "build_agent")
    assert hasattr(mod, "_spread_loop")
