"""Unit tests for the dashboard backend (Phase 2, plan 02-05).

Pins the WebSocket message protocol contract, the server-side grid-snap
behaviour, and the kv_source / subject_source wildcard suffix invariants
(carry-forward of Phase 1's `*` vs `>` bug discovered by 01-10).

Per the plan body the tests cover three concerns:

1. Click-handler logic (write CellState; delete on null temperature; snap to
   grid via ``cell_indices`` + ``cell_center``). Exercised against
   ``AgentMesh.local()`` so the KV side effect is real.
2. kv_source replay → broadcaster fan-out (cell PUT yields a ``cell_update``
   payload with the snapped indices).
3. Source-text gates: every ``mesh.kv_source(...)`` pattern ends in ``.>`` or
   ``.*``; legacy contracts and the kwargs banned by A-09
   (``bucket=``, ``prefix=``, ``model=``) are absent.

Plus the shape of ``make_app(mesh)`` (FastAPI TestClient hits ``/health``)
and the public protocol-constant exports (``MSG_CELL_UPDATE`` etc.) the
02-09 integration test will reference.
"""

from __future__ import annotations

import asyncio
import re
import socket
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from demos.wildfire.core.config import (
    FIRE_SIM_AMBIENT_C,
    SPAWN_MAGNITUDE_LARGE,
    SPAWN_MAGNITUDE_MEDIUM,
)
from demos.wildfire.core.contracts import CellState, Coords
from demos.wildfire.core.keys import (
    CELL_PREFIX,
    cell_center,
    cell_indices,
    cell_key,
)
from openagentmesh import AgentMesh

from demos.wildfire.dashboard import server as dashboard_server
from demos.wildfire.dashboard.server import (
    MSG_ACTION_STATUS,
    MSG_CELL_DELETE,
    MSG_CELL_UPDATE,
    MSG_DETECTION,
    MSG_FLEET_UPDATE,
    handle_click,
    make_app,
    register_mesh_consumers,
)


SERVER_SRC = Path(dashboard_server.__file__).read_text()


# ---------------------------------------------------------------------------
# 1. Click-handler logic
# ---------------------------------------------------------------------------


def _live_cell_entries(raw_entries):
    """Filter raw KV entries to live PUTs and validate each as CellState.

    ``mesh.kv.list_models`` chokes on DELETE tombstones (empty bytes do not
    parse as JSON), so we project the raw byte entries here. The KV
    snapshot may surface a tombstone with ``operation="PUT"`` and an empty
    value when nats-py's history coalesces a delete; we treat empty values
    as absent regardless of the reported operation.
    """
    out = []
    for e in raw_entries:
        if e.operation != "PUT":
            continue
        if not e.value:
            continue  # tombstone (delete) reported as empty PUT.
        out.append((e.key, CellState.model_validate_json(e.value), e.revision))
    return out


@pytest.mark.asyncio
async def test_click_writes_cellstate() -> None:
    """A click with a non-null temperature writes a CellState to KV at the
    snapped grid key with ``last_modified_by == mesh.instance_id``."""
    async with AgentMesh.local() as mesh:
        await handle_click(mesh, x=1.5, y=-2.0, temperature=SPAWN_MAGNITUDE_LARGE)

        live = _live_cell_entries(await mesh.kv.list(f"{CELL_PREFIX}.>"))
        assert len(live) == 1
        key, value, _ = live[0]
        assert value.temperature == SPAWN_MAGNITUDE_LARGE
        assert value.last_modified_by == mesh.instance_id

        # Snapped coords should match cell_center(cell_indices(x, y)).
        x_idx, y_idx = cell_indices(1.5, -2.0)
        center = cell_center(x_idx, y_idx)
        assert value.coords.x == pytest.approx(center.x)
        assert value.coords.y == pytest.approx(center.y)
        assert key == cell_key(1.5, -2.0)


@pytest.mark.asyncio
async def test_click_with_null_temperature_deletes_cell() -> None:
    """Click with ``temperature=None`` deletes the cell key (off-cycle)."""
    async with AgentMesh.local() as mesh:
        # Pre-write a CellState so there is something to delete.
        x_idx, y_idx = cell_indices(0.4, 0.4)
        snapped = cell_center(x_idx, y_idx)
        await mesh.kv.put_model(
            cell_key(0.4, 0.4),
            CellState(
                coords=snapped,
                temperature=SPAWN_MAGNITUDE_MEDIUM,
                last_modified_at=time.time(),
                last_modified_by="seed",
            ),
        )

        await handle_click(mesh, x=0.4, y=0.4, temperature=None)

        # After the delete, list either omits the key or surfaces it with
        # operation="DELETE". Either way, no live PUT entry remains.
        live = [
            (k, v, r)
            for (k, v, r) in _live_cell_entries(await mesh.kv.list(f"{CELL_PREFIX}.>"))
            if k == cell_key(0.4, 0.4)
        ]
        assert live == []


@pytest.mark.asyncio
async def test_click_with_ambient_temperature_deletes_cell() -> None:
    """Per D-50, ``temperature == FIRE_SIM_AMBIENT_C`` is treated as 'off'."""
    async with AgentMesh.local() as mesh:
        x_idx, y_idx = cell_indices(-1.0, 1.0)
        snapped = cell_center(x_idx, y_idx)
        await mesh.kv.put_model(
            cell_key(-1.0, 1.0),
            CellState(
                coords=snapped,
                temperature=SPAWN_MAGNITUDE_MEDIUM,
                last_modified_at=time.time(),
                last_modified_by="seed",
            ),
        )

        await handle_click(mesh, x=-1.0, y=1.0, temperature=FIRE_SIM_AMBIENT_C)

        live = [
            (k, v, r)
            for (k, v, r) in _live_cell_entries(await mesh.kv.list(f"{CELL_PREFIX}.>"))
            if k == cell_key(-1.0, 1.0)
        ]
        assert live == []


@pytest.mark.asyncio
async def test_click_snaps_to_grid_exactly() -> None:
    """Server is the only authority for cell-key derivation (D-52).

    A noisy float input snaps to ``cell_center(cell_indices(x, y))`` exactly;
    the browser-supplied raw coords are NEVER persisted as-is.
    """
    raw_x, raw_y = 1.234, -2.789
    expected_x_idx, expected_y_idx = cell_indices(raw_x, raw_y)
    expected_center = cell_center(expected_x_idx, expected_y_idx)

    async with AgentMesh.local() as mesh:
        await handle_click(mesh, x=raw_x, y=raw_y, temperature=SPAWN_MAGNITUDE_LARGE)

        live = _live_cell_entries(await mesh.kv.list(f"{CELL_PREFIX}.>"))
        assert len(live) == 1
        key, value, _ = live[0]
        assert value.coords.x == pytest.approx(expected_center.x)
        assert value.coords.y == pytest.approx(expected_center.y)
        assert key == f"{CELL_PREFIX}.{expected_x_idx}.{expected_y_idx}"


@pytest.mark.asyncio
async def test_click_delete_swallows_missing_key() -> None:
    """Deleting an absent cell is a no-op, not an exception."""
    async with AgentMesh.local() as mesh:
        # Key was never written — delete must not raise.
        await handle_click(mesh, x=2.5, y=2.5, temperature=None)


# ---------------------------------------------------------------------------
# 2. kv_source replay → broadcaster fan-out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kv_source_broadcasts_cell_update() -> None:
    """Writing a CellState fires the dashboard's broadcaster with a
    ``cell_update`` envelope carrying the parsed indices and snapped coords.
    """
    received: list[dict] = []

    async def fake_broadcast(msg: dict) -> None:
        received.append(msg)

    async with AgentMesh.local() as mesh:
        register_mesh_consumers(mesh, fake_broadcast)
        # AgentMesh.local() already entered __aenter__; the source bindings
        # need a re-subscribe pass since register happens after entry.
        await mesh._subscribe_pending()

        # Write a cell. The dashboard's kv_source handler should fan out a
        # ``cell_update`` event to fake_broadcast.
        x_idx, y_idx = cell_indices(0.0, 0.0)
        center = cell_center(x_idx, y_idx)
        await mesh.kv.put_model(
            cell_key(0.0, 0.0),
            CellState(
                coords=center,
                temperature=SPAWN_MAGNITUDE_LARGE,
                last_modified_at=time.time(),
                last_modified_by="seed",
            ),
        )

        # Allow the kv_source watcher task to pick up the write.
        for _ in range(50):
            cell_updates = [m for m in received if m.get("type") == MSG_CELL_UPDATE]
            if cell_updates:
                break
            await asyncio.sleep(0.05)

        cell_updates = [m for m in received if m.get("type") == MSG_CELL_UPDATE]
        assert cell_updates, f"no cell_update broadcast; got {received}"
        msg = cell_updates[-1]
        assert msg["temperature"] == SPAWN_MAGNITUDE_LARGE
        assert msg["x_idx"] == x_idx
        assert msg["y_idx"] == y_idx


# ---------------------------------------------------------------------------
# 3. Source-text gates
# ---------------------------------------------------------------------------


def test_kv_source_uses_wildcard_suffix() -> None:
    """Every ``mesh.kv_source(<pattern>, ...)`` first arg ends in ``.>`` or
    ``.*``. Phase 1's 01-10 integration tests discovered that bare prefixes
    (e.g. ``"wildfire.world.cell"``) silently never fire on real keys.
    """
    pattern_re = re.compile(r"""mesh\.kv_source\(\s*(?:f?["'])([^"']+)["']""")
    found = pattern_re.findall(SERVER_SRC)
    assert found, "no mesh.kv_source(...) calls found in server source"
    for pat in found:
        # Allow plain string `wildfire.world.cell.>` AND f-string composed
        # patterns like `f"{CELL_PREFIX}.>"` which keep the same suffix.
        assert pat.endswith(".>") or pat.endswith(".*"), (
            f"kv_source pattern {pat!r} must end in '.>' or '.*'"
        )


def test_subject_source_for_action_status() -> None:
    """``mesh.subject_source(\"mesh.action.>\")`` is wired for the action
    fleet status feed broadcast (D-45, plan 02-09 integration target)."""
    assert "mesh.subject_source(" in SERVER_SRC
    assert "mesh.action.>" in SERVER_SRC


def test_negative_gates_no_legacy_contracts() -> None:
    """Pre-amendment names must not appear (per A-09)."""
    banned = [
        "ThermalGrid",
        "FireSpawn",
        "FireSuppress",
        "mesh.environment.thermal",
        "mesh.fire.spawn",
        "mesh.fire.suppress",
    ]
    for name in banned:
        assert name not in SERVER_SRC, f"banned contract or subject {name!r} in server source"


def test_negative_gates_no_kwargs_a09() -> None:
    """Per A-09 the SDK API is positional: no ``bucket=``, ``prefix=`` or
    ``model=`` kwargs (these were ergonomic experiments that lost out)."""
    for line in SERVER_SRC.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for kw in ("bucket=", "prefix=", "model="):
            assert kw not in line, f"banned kwarg {kw!r} on line: {line}"


def test_grep_invariants_match_plan_body() -> None:
    """Mirror the plan body's grep invariants in test form."""
    assert SERVER_SRC.count("def make_app") == 1
    assert SERVER_SRC.count("WebSocket") >= 1
    assert SERVER_SRC.count("mesh.kv_source(") == 3
    assert SERVER_SRC.count("mesh.subject_source(") == 1
    assert SERVER_SRC.count("mesh.kv.put_model(") >= 1
    assert SERVER_SRC.count("mesh.kv.delete(") >= 1
    # The two patterns that demand `.>` (per the segment-count rule).
    assert "wildfire.world.cell.>" in SERVER_SRC or "{CELL_PREFIX}.>" in SERVER_SRC
    assert "wildfire.fleet.>" in SERVER_SRC or "{FLEET_PREFIX}.>" in SERVER_SRC


# ---------------------------------------------------------------------------
# 4. Public protocol constants + /health endpoint
# ---------------------------------------------------------------------------


def test_websocket_message_protocol_constants_exported() -> None:
    """The five message-type constants are importable from the module so the
    02-09 integration test can reference them by name (no magic strings).
    """
    assert MSG_CELL_UPDATE == "cell_update"
    assert MSG_CELL_DELETE == "cell_delete"
    assert MSG_FLEET_UPDATE == "fleet_update"
    assert MSG_DETECTION == "detection"
    assert MSG_ACTION_STATUS == "action_status"


@pytest.mark.asyncio
async def test_health_endpoint_shape() -> None:
    """``GET /health`` returns 200 with mesh.instance_id and a connection count."""
    async with AgentMesh.local() as mesh:
        app = make_app(mesh)
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["mesh_instance_id"] == mesh.instance_id
            assert body["connections"] == 0


# ---------------------------------------------------------------------------
# 5. find_free_port (Task 2 helper exposed for unit testing) — RED tests
# ---------------------------------------------------------------------------


def test_find_free_port_returns_requested_when_available() -> None:
    """When the requested port is free, ``find_free_port`` returns it as-is."""
    from demos.wildfire.dashboard.__main__ import find_free_port

    # Pick a random ephemeral port that we know is free, then ask for it.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    # Now `free_port` is closed/free; find_free_port should return it.
    chosen = find_free_port("127.0.0.1", free_port)
    assert chosen == free_port


def test_find_free_port_walks_when_busy() -> None:
    """When the requested port is occupied, ``find_free_port`` walks to a
    free neighbour and returns a different port.
    """
    from demos.wildfire.dashboard.__main__ import find_free_port

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    busy_port = sock.getsockname()[1]
    try:
        chosen = find_free_port("127.0.0.1", busy_port)
        assert chosen != busy_port
        assert chosen > busy_port
    finally:
        sock.close()


def test_main_module_exposes_callable_main() -> None:
    """``python -m demos.wildfire.dashboard`` resolves to a callable ``main``."""
    import demos.wildfire.dashboard.__main__ as m

    assert callable(m.main)


def test_main_source_text_gates() -> None:
    """Source-text gates for ``__main__.py`` (mirror plan invariants)."""
    from demos.wildfire.dashboard import __main__ as main_mod

    src = Path(main_mod.__file__).read_text()
    assert "find_free_port" in src
    assert "uvicorn" in src
    assert "DASHBOARD_PORT" in src
    assert "pnpm run build" in src
    assert "dist" in src and "index.html" in src
    # A-09 negative gates.
    for line in src.splitlines():
        if line.strip().startswith("#"):
            continue
        for kw in ("bucket=", "prefix=", "model="):
            assert kw not in line, f"banned kwarg {kw!r} on line: {line}"
