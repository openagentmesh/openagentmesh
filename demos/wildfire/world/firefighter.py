"""Firefighter operator CLI -- typed-form dispatch caller (SCN-10).

Phase 2 plain caller process. Reads typed lines from stdin, parses each line
into a ``DispatchOrder``, and calls the matching action fleet via
``mesh.call``. Prints the resolved ``DispatchAck`` to stdout.

This module is a **plain caller** -- it is NOT a registered ``@mesh.agent``
(per ``km/specs/wildfire/firefighter.md`` "plain caller process; not a
registered agent" + decision D-30). It instantiates ``AgentMesh()``,
opens the connection, runs the REPL, and exits. No catalog presence,
no @mesh.agent decoration, no AgentSpec.

Phase 3 deferrals (D-32): no briefing-pane subscription on the briefing
fan-out subject, and no NL-translation hop through the Phase-3 translator
agent. Phase 3 will retrofit a ``--nl`` flag (default true) that adds the
NL translation step; ``--typed`` falls back to the path this module ships
today.

Typed-form grammar (D-31)::

    <fleet> <x> <y> <priority> [persons]

Fields:

- ``fleet``     one of ``heli``, ``ffunit``, ``medevac`` (case-insensitive).
- ``x``, ``y``  floats in km, both bounded to [-5, +5] by the ``Coords``
                pydantic validator. Out-of-range values raise ``ValueError``.
- ``priority``  one of ``low``, ``med``, ``high`` (case-insensitive).
- ``persons``   optional integer; defaults to 0. Only meaningful for
                medevac. The parser does NOT enforce that non-medevac
                fleets pass 0 -- the spec says persons defaults to 0 for
                non-medevac, but parsing should not reject. The heli /
                ffunit handlers ignore the field.

The REPL also accepts ``help`` and ``?`` (prints the grammar) and treats
empty lines as no-ops. EOF (Ctrl-D) exits with code 0. A bad input line
prints the grammar to stderr and continues (loud failure per D-31).

Channel routing (per ADR-0049 + km/specs/wildfire/firefighter.md):

==========  =========================
fleet       target agent name
==========  =========================
heli        low-alt.heli
ffunit      ground.ffunit
medevac     ground.medevac
==========  =========================

Run as a module::

    python -m demos.wildfire.world.firefighter

Env:
    NATS_URL    default ``nats://127.0.0.1:4222``.

Decision references: SCN-10 (operator dispatcher requirement), D-30 (plain
caller process), D-31 (typed-form grammar), D-32 (Phase 3 defers briefing
pane + NL translator), D-33 (run in a separate terminal alongside the
orchestrator).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid

from demos.wildfire.core.contracts import Coords, DispatchOrder

from openagentmesh import AgentMesh
from openagentmesh._errors import MeshError

# ---------------------------------------------------------------------------
# Grammar reminder (printed on bad input + on `help` / `?`)
# ---------------------------------------------------------------------------

GRAMMAR = (
    "grammar: <fleet> <x> <y> <priority> [persons]\n"
    "  fleet     one of: heli | ffunit | medevac\n"
    "  x, y      coords in km, each in [-5.0, 5.0]\n"
    "  priority  one of: low | med | high\n"
    "  persons   optional int (defaults to 0; only used by medevac)\n"
    "examples:\n"
    "  heli 1.5 -2.3 high\n"
    "  ffunit 0 0 low\n"
    "  medevac 2.7 1.2 med 3\n"
    "type 'help' or '?' to reprint this grammar, Ctrl-D to exit"
)

# Fleet -> target agent name (channel.<fleet>) per firefighter.md.
_FLEET_TO_TARGET: dict[str, str] = {
    "heli":    "low-alt.heli",
    "ffunit":  "ground.ffunit",
    "medevac": "ground.medevac",
}

_VALID_PRIORITIES: set[str] = {"low", "med", "high"}


# ---------------------------------------------------------------------------
# Pure helpers (no I/O, no SDK)
# ---------------------------------------------------------------------------


def target_agent_for_fleet(fleet: str) -> str:
    """Return the action-fleet agent name for a given fleet keyword.

    >>> target_agent_for_fleet("heli")
    'low-alt.heli'

    Raises ``ValueError`` for unknown fleets.
    """
    key = fleet.lower()
    if key not in _FLEET_TO_TARGET:
        raise ValueError(
            f"unknown fleet {fleet!r}: expected one of "
            f"{sorted(_FLEET_TO_TARGET)}"
        )
    return _FLEET_TO_TARGET[key]


def parse_dispatch_line(line: str) -> DispatchOrder | None:
    """Parse one stripped line into a ``DispatchOrder`` template.

    The returned order has placeholder ``order_id``, ``operator_id``, and
    ``issued_at`` values; the REPL fills those in before dispatching.
    The caller does NOT need to set ``incident_id`` -- Phase 2 leaves it
    None (no briefer wiring).

    Returns ``None`` for empty lines and for the ``help`` / ``?``
    pseudo-commands. Raises ``ValueError`` with a human-readable message
    on bad input. The function never raises anything other than
    ``ValueError`` (the REPL catches ``ValueError`` to keep the loop
    alive).
    """
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.lower() in {"help", "?"}:
        return None

    tokens = stripped.split()
    if len(tokens) < 4 or len(tokens) > 5:
        raise ValueError(
            f"expected 4 or 5 fields, got {len(tokens)}: {stripped!r}"
        )

    fleet = tokens[0].lower()
    if fleet not in _FLEET_TO_TARGET:
        raise ValueError(
            f"unknown fleet {tokens[0]!r}: expected one of "
            f"{sorted(_FLEET_TO_TARGET)}"
        )

    try:
        x = float(tokens[1])
        y = float(tokens[2])
    except ValueError as e:
        raise ValueError(f"x and y must be floats: {e}") from e

    priority = tokens[3].lower()
    if priority not in _VALID_PRIORITIES:
        raise ValueError(
            f"unknown priority {tokens[3]!r}: expected one of "
            f"{sorted(_VALID_PRIORITIES)}"
        )

    persons = 0
    if len(tokens) == 5:
        try:
            persons = int(tokens[4])
        except ValueError as e:
            raise ValueError(f"persons must be an int: {e}") from e

    # Coords validates the [-5, +5] bound; surface its ValidationError as
    # ValueError so the REPL's ValueError catch covers both shapes.
    try:
        coords = Coords(x=x, y=y)
    except Exception as e:
        raise ValueError(f"coords out of bounds: {e}") from e

    # Placeholder values for caller-injected fields. The REPL overwrites
    # order_id / operator_id / issued_at before dispatching.
    return DispatchOrder(
        order_id="",
        target_coords=coords,
        priority=priority,  # type: ignore[arg-type]
        operator_id="",
        issued_at=0.0,
        persons_estimated=persons,
    )


def format_ack(ack: dict) -> str:
    """Format a ``DispatchAck`` dict (the wire shape returned by ``mesh.call``)
    as a single human-readable line.
    """
    accepted = ack.get("accepted")
    instance_id = ack.get("instance_id")
    eta = ack.get("eta_seconds")
    reason = ack.get("reason")
    eta_str = f"{eta}s" if eta is not None else "None"
    return (
        f"ack: accepted={accepted} instance_id={instance_id} "
        f"eta={eta_str} reason={reason}"
    )


# ---------------------------------------------------------------------------
# CLI entry point (Task 2 wires the REPL; Task 1 just declares main).
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    """Entry point. Parses optional flags, opens AgentMesh, runs the REPL.

    Task 2 fills this in. Task 1 leaves a stub so the module is importable
    and ``main`` is callable without crashing.
    """
    parser = argparse.ArgumentParser(prog="firefighter")
    parser.add_argument(
        "--operator-id",
        default=None,
        help="operator identifier (default: derived from mesh.instance_id)",
    )
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
