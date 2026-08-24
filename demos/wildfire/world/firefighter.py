"""Firefighter operator CLI -- typed-form dispatch caller (SCN-10).

Phase 2 plain caller process. Reads typed lines from stdin, parses each line
into a ``DispatchOrder``, and calls the matching action fleet via
``mesh.call``. Prints the resolved ``DispatchAck`` to stdout.

This module is a **plain caller** -- it is NOT a registered ``@mesh.agent``
(per ``km/specs/wildfire/firefighter.md`` "plain caller process; not a
registered agent" + decision D-30). It instantiates ``AgentMesh()``,
opens the connection, runs the REPL, and exits. No catalog presence,
no @mesh.agent decoration, no AgentSpec.

Phase 3 (D-32) retrofit: NL mode is the default. Any line that does not
parse as the typed grammar is audited on ``mesh.fire.{operator_id}.intent``
(``FirefighterIntent``) and translated via ``mesh.call("tasker", ...)`` into
a ``TaskCommand``; the operator confirms (or ``--auto-accept`` skips the
prompt) and the command dispatches to the matching fleet. ``--typed``
restores the grammar-only behaviour. The briefing-pane subscription stays
deferred (the scenario UI owns that surface).

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
import contextlib
import os
import sys
import time
import uuid

from demos.wildfire.core.contracts import (
    Coords,
    DispatchOrder,
    FirefighterIntent,
    TaskCommand,
    TaskTranslateRequest,
)
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
    "in --nl mode (default) any other sentence goes to the tasker, e.g.:\n"
    "  send the water bomber to the big fire, high priority\n"
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
        priority=priority,  # ty: ignore[invalid-argument-type]
        operator_id="",
        issued_at=0.0,
        persons_estimated=persons,
    )


def dispatch_order_from_command(cmd: TaskCommand, *, operator_id: str) -> DispatchOrder:
    """Project a tasker ``TaskCommand`` onto a ready-to-send ``DispatchOrder``."""
    return DispatchOrder(
        order_id=uuid.uuid4().hex,
        target_coords=cmd.coords,
        incident_id=cmd.incident_id,
        priority=cmd.priority,
        operator_id=operator_id,
        issued_at=time.time(),
        persons_estimated=cmd.persons_estimated,
    )


def format_command(cmd: TaskCommand) -> str:
    """One-line human rendering of a tasker translation."""
    return (
        f"tasker: {cmd.target_fleet} @ ({cmd.coords.x:.2f}, {cmd.coords.y:.2f}) "
        f"priority={cmd.priority} persons={cmd.persons_estimated}\n"
        f"  rationale: {cmd.rationale}"
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
# REPL loop (Task 2)
# ---------------------------------------------------------------------------


_PROMPT_BANNER = (
    "firefighter operator: type 'help' for grammar; Ctrl-D to exit"
)
_PROMPT = "> "


async def repl(
    mesh: AgentMesh,
    *,
    operator_id: str,
    in_stream=None,
    out_stream=None,
    err_stream=None,
    call_timeout: float = 10.0,
    nl: bool = True,
    auto_accept: bool = False,
) -> None:
    """Run the read-eval-print loop against an open ``AgentMesh``.

    Each iteration:

    1. Print ``> `` and read one line via ``asyncio.to_thread(readline)``
       so the loop yields to the event loop while waiting on stdin.
    2. Empty string back from ``readline`` signals EOF (stdin closed):
       break and return.
    3. ``help`` / ``?`` print ``GRAMMAR`` to stdout.
    4. Otherwise, parse the line:
       - ``ValueError`` -> print ``error: <msg>`` and ``GRAMMAR`` to
         stderr; continue (loud failure per D-31).
       - parsed ``DispatchOrder`` -> stamp ``order_id`` (uuid4 hex),
         ``operator_id`` (caller-supplied), and ``issued_at`` (now); look
         up the target via ``target_agent_for_fleet``; ``mesh.call`` it.
       - ``MeshError`` from the call -> print to stderr; continue.

    The streams default to the live process streams. Tests pass
    ``StringIO`` instances to drive the loop deterministically.
    """
    if in_stream is None:
        in_stream = sys.stdin
    if out_stream is None:
        out_stream = sys.stdout
    if err_stream is None:
        err_stream = sys.stderr

    print(_PROMPT_BANNER, file=out_stream)

    while True:
        # Print the prompt without trailing newline; flush so it appears
        # before readline blocks. StringIO ignores flush; real stdout needs it.
        out_stream.write(_PROMPT)
        with contextlib.suppress(Exception):
            out_stream.flush()

        # Read one line. asyncio.to_thread keeps stdin off the event-loop
        # thread; for StringIO this is functionally synchronous but the
        # await still yields once.
        line = await asyncio.to_thread(in_stream.readline)
        if line == "":  # EOF (Ctrl-D on a tty, end-of-StringIO in tests)
            break

        stripped = line.strip()
        if not stripped:
            continue

        if stripped.lower() in {"help", "?"}:
            print(GRAMMAR, file=out_stream)
            continue

        try:
            order_template = parse_dispatch_line(line)
        except ValueError as e:
            if nl:
                # D-32 NL mode: anything that is not the typed grammar goes
                # through the tasker. Audit first, then translate.
                await _handle_nl_line(
                    mesh,
                    text=stripped,
                    operator_id=operator_id,
                    in_stream=in_stream,
                    out_stream=out_stream,
                    err_stream=err_stream,
                    call_timeout=call_timeout,
                    auto_accept=auto_accept,
                )
                continue
            print(f"error: {e}", file=err_stream)
            print(GRAMMAR, file=err_stream)
            continue

        if order_template is None:
            # Belt-and-braces: parse_dispatch_line already returned None
            # for help / ? above. Defensive guard for empty lines that
            # somehow slipped past the strip() check.
            continue

        # Recover the fleet keyword (first whitespace-separated token,
        # lowered) so we can route to the matching action agent.
        fleet = stripped.split()[0].lower()
        try:
            target = target_agent_for_fleet(fleet)
        except ValueError as e:
            print(f"error: {e}", file=err_stream)
            continue

        # Stamp caller-side fields. Order id is unique per dispatch so
        # the receiving agent can dedupe / log.
        order = order_template.model_copy(
            update={
                "order_id": uuid.uuid4().hex,
                "operator_id": operator_id,
                "issued_at": time.time(),
            }
        )

        try:
            ack = await mesh.call(target, order, timeout=call_timeout)
        except MeshError as e:
            print(f"error: dispatch failed: {e}", file=err_stream)
            continue
        except Exception as e:  # pragma: no cover -- defensive
            print(f"error: dispatch failed: {e}", file=err_stream)
            continue

        print(format_ack(ack), file=out_stream)


async def _handle_nl_line(
    mesh: AgentMesh,
    *,
    text: str,
    operator_id: str,
    in_stream,
    out_stream,
    err_stream,
    call_timeout: float,
    auto_accept: bool,
) -> None:
    """NL path: audit intent, translate via tasker, confirm, dispatch.

    Failure shape per the tasker spec: an ``llm_unavailable`` MeshError
    prints and re-prompts; it never kills the REPL.
    """
    # Audit trail (mesh.fire.{operator_id}.intent, contracts.md).
    try:
        await mesh.publish(
            f"mesh.fire.{operator_id}.intent",
            FirefighterIntent(operator_id=operator_id, text=text, issued_at=time.time()),
        )
    except Exception as e:
        print(f"warn: intent audit publish failed: {e}", file=err_stream)

    print("tasker is translating…", file=out_stream)
    try:
        raw = await mesh.call(
            "tasker",
            TaskTranslateRequest(operator_id=operator_id, text=text),
            timeout=call_timeout,
        )
        cmd = TaskCommand.model_validate(raw)
    except MeshError as e:
        print(f"error: {e}", file=err_stream)
        return
    except Exception as e:
        print(f"error: translation failed: {e}", file=err_stream)
        return

    print(format_command(cmd), file=out_stream)

    if not auto_accept:
        out_stream.write("dispatch? [y/N] ")
        with contextlib.suppress(Exception):
            out_stream.flush()
        answer = (await asyncio.to_thread(in_stream.readline)).strip().lower()
        if answer not in {"y", "yes"}:
            print("cancelled", file=out_stream)
            return

    order = dispatch_order_from_command(cmd, operator_id=operator_id)
    target = target_agent_for_fleet(cmd.target_fleet)
    try:
        ack = await mesh.call(target, order, timeout=call_timeout)
    except MeshError as e:
        print(f"error: dispatch failed: {e}", file=err_stream)
        return
    print(format_ack(ack), file=out_stream)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _run(
    url: str, operator_id: str | None, *, nl: bool, auto_accept: bool
) -> None:
    """Open ``AgentMesh(url)``, derive operator id if needed, run the REPL."""
    async with AgentMesh(url) as mesh:
        op_id = operator_id or f"op-{mesh.instance_id[:8]}"
        await repl(mesh, operator_id=op_id, nl=nl, auto_accept=auto_accept)


def main(argv: list[str]) -> int:
    """Entry point. Parses optional flags, opens AgentMesh, runs the REPL.

    Returns 0 on clean exit (EOF or KeyboardInterrupt), 1 on connection /
    runtime failure. Bad lines do NOT exit the REPL; they are handled
    inside the loop.
    """
    parser = argparse.ArgumentParser(prog="firefighter")
    parser.add_argument(
        "--operator-id",
        default=None,
        help="operator identifier (default: derived from mesh.instance_id)",
    )
    parser.add_argument(
        "--typed",
        action="store_true",
        help="typed-grammar only: non-grammar lines are errors (disables the NL tasker path)",
    )
    parser.add_argument(
        "--auto-accept",
        action="store_true",
        help="dispatch tasker translations without the y/N confirmation",
    )
    args = parser.parse_args(argv)

    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")

    try:
        asyncio.run(
            _run(
                url,
                args.operator_id,
                nl=not args.typed,
                auto_accept=args.auto_accept,
            )
        )
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"firefighter exited with error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
