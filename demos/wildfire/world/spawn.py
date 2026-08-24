"""Spawn CLI (D-05, D-06, D-07, A-06).

Writes a ``CellState`` directly to ``wildfire.world.cell.<x_idx>.<y_idx>``
in the OAM-internal ``mesh-context`` bucket (single-bucket collapse per A-02).

The CLI is the viewer's only input surface for Phase 1 (no scenario UI yet).
It snaps the input ``(x, y)`` to the 200 m grid via :func:`cell_indices` and
:func:`cell_center`, sets ``last_modified_by = mesh.instance_id`` so fire-sim's
self-write filter handles its own deltas correctly, and exits zero.

Per A-06 / A-08 the CLI does NOT publish on any pubsub subject; the KV
write is the only side effect. Per D-07 there is no ``--seed`` /
``--scenario`` flag in Phase 1; reproducibility is a Phase 5 concern.

Usage::

    python -m demos.wildfire.world.spawn 1.5 -2.3 600
                                          ^   ^    ^
                                          x   y    temp_celsius

Env:
    NATS_URL  (default: ``nats://127.0.0.1:4222``)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

from demos.wildfire.core.contracts import CellState, Coords
from demos.wildfire.core.keys import cell_center, cell_indices, cell_key
from openagentmesh import AgentMesh

USAGE = "usage: python -m demos.wildfire.world.spawn <x> <y> <temp_celsius>"


async def _spawn(x: float, y: float, temp: float) -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    async with AgentMesh(url) as mesh:
        x_idx, y_idx = cell_indices(x, y)
        key = cell_key(x, y)
        snapped = cell_center(x_idx, y_idx)
        state = CellState(
            coords=snapped,
            temperature=temp,
            last_modified_at=time.time(),
            last_modified_by=mesh.instance_id,
        )
        await mesh.kv.put_model(key, state)
        print(f"wrote {key} temp={temp} by={mesh.instance_id}")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        x = float(argv[0])
        y = float(argv[1])
        temp = float(argv[2])
    except ValueError:
        print(USAGE, file=sys.stderr)
        return 2
    # Coords enforces the [-5, +5] bound via Pydantic; cell_indices is a pure
    # math helper and does NOT validate. Validate before connecting so an
    # out-of-bounds spawn never opens a NATS connection.
    try:
        Coords(x=x, y=y)
    except Exception as e:
        print(f"out of bounds: {e}", file=sys.stderr)
        return 2
    try:
        asyncio.run(_spawn(x, y, temp))
    except Exception as e:
        print(f"spawn failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
