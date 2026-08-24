"""Unit tests for the firefighter operator CLI (SCN-10, D-30, D-31, D-32, D-33).

Behavior under test
-------------------

The firefighter CLI is a **plain caller process** -- it instantiates
``AgentMesh()`` and uses ``mesh.call`` to dispatch typed orders to the
heli / ffunit / medevac fleets. It does NOT register a ``@mesh.agent``
(per ``km/specs/wildfire/firefighter.md`` "plain caller process; not a
registered agent" + D-30) and it does NOT subscribe to ``mesh.briefing.>``
(deferred to Phase 3 per D-32).

Phase 2 (this plan) ships the typed-form grammar (D-31)::

    <fleet> <x> <y> <priority> [persons]

Phase 3 will retrofit a ``--nl`` flag that goes through Tasker; the typed
path stays as the ``--typed`` fallback.

Test layout
-----------

1. Pure-helper tests (Task 1): grammar parsing, channel routing, ack
   formatting. No NATS, no ``AgentMesh``.
2. Source-text negative gates (Task 1): assert the module file does NOT
   contain forbidden phrases (decorator usage, sources, briefing
   subscription, dropped artefacts).
3. Live REPL tests (Task 2): drive ``repl()`` against ``AgentMesh.local()``
   with stub responder agents standing in for the action fleets.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

# The module under test is created by this very plan; importorskip keeps the
# failing-import-at-collection error short and explicit if RED is mis-driven.
firefighter = pytest.importorskip(
    "demos.wildfire.world.firefighter",
    reason="demos.wildfire.world.firefighter not yet on disk (this plan creates it).",
)

from demos.wildfire.core.contracts import (  # noqa: E402
    Coords,
    DispatchAck,
    DispatchOrder,
    TaskCommand,
    TaskTranslateRequest,
)

_FIREFIGHTER_PATH = Path(firefighter.__file__)


# ---------------------------------------------------------------------------
# Task 1: pure parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, expected_target, expected_priority, expected_persons, expected_x, expected_y",
    [
        ("heli 1.0 1.0 high",        "low-alt.heli",   "high", 0, 1.0,  1.0),
        ("medevac 0 0 low 2",        "ground.medevac", "low",  2, 0.0,  0.0),
        ("ffunit -3.5 4.2 med",      "ground.ffunit",  "med",  0, -3.5, 4.2),
        ("HELI 2 -2 HIGH",           "low-alt.heli",   "high", 0, 2.0,  -2.0),  # case-insensitive
    ],
)
def test_parse_typed_dispatch_line_valid(
    line, expected_target, expected_priority, expected_persons, expected_x, expected_y
):
    order = firefighter.parse_dispatch_line(line)
    assert order is not None
    assert isinstance(order, DispatchOrder)
    assert order.target_coords.x == expected_x
    assert order.target_coords.y == expected_y
    assert order.priority == expected_priority
    assert order.persons_estimated == expected_persons
    # parse_dispatch_line records the fleet (we recover it via the helper).
    fleet = line.strip().split()[0].lower()
    assert firefighter.target_agent_for_fleet(fleet) == expected_target


def test_parse_returns_none_for_help_or_empty():
    assert firefighter.parse_dispatch_line("") is None
    assert firefighter.parse_dispatch_line("   ") is None
    assert firefighter.parse_dispatch_line("help") is None
    assert firefighter.parse_dispatch_line("?") is None
    assert firefighter.parse_dispatch_line("HELP") is None


def test_parse_raises_on_unknown_fleet():
    with pytest.raises(ValueError):
        firefighter.parse_dispatch_line("ufo 0 0 high")


def test_parse_raises_on_bad_priority():
    with pytest.raises(ValueError):
        firefighter.parse_dispatch_line("heli 0 0 critical")


def test_parse_raises_on_out_of_bounds_coords():
    # Coords pydantic validator rejects > 5.
    with pytest.raises(ValueError):
        firefighter.parse_dispatch_line("heli 99 0 high")
    with pytest.raises(ValueError):
        firefighter.parse_dispatch_line("heli 0 -99 high")


def test_parse_raises_on_field_count_too_few():
    with pytest.raises(ValueError):
        firefighter.parse_dispatch_line("heli 0 0")


def test_parse_raises_on_field_count_too_many():
    with pytest.raises(ValueError):
        # 6 tokens: extra trailing junk.
        firefighter.parse_dispatch_line("heli 0 0 high 3 extra")


def test_parse_raises_on_non_float_coords():
    with pytest.raises(ValueError):
        firefighter.parse_dispatch_line("heli foo 0 high")


def test_parse_raises_on_non_int_persons():
    with pytest.raises(ValueError):
        firefighter.parse_dispatch_line("medevac 0 0 high notanint")


def test_parse_persons_optional_default_zero():
    order = firefighter.parse_dispatch_line("heli 0 0 high")
    assert order is not None
    assert order.persons_estimated == 0


def test_parse_persons_only_medevac_meaningful():
    """Parser does NOT enforce that only medevac uses persons. The
    spec says persons defaults to 0 for non-medevac, but parsing should
    not reject -- the operator can dispatch with persons=3 to heli if
    they want; the heli handler ignores the field. Documented in the
    module docstring.
    """
    medevac_order = firefighter.parse_dispatch_line("medevac 0 0 high 3")
    assert medevac_order.persons_estimated == 3
    heli_order = firefighter.parse_dispatch_line("heli 0 0 high 3")
    assert heli_order.persons_estimated == 3  # accepted; handler will ignore


def test_target_agent_mapping():
    assert firefighter.target_agent_for_fleet("heli") == "low-alt.heli"
    assert firefighter.target_agent_for_fleet("ffunit") == "ground.ffunit"
    assert firefighter.target_agent_for_fleet("medevac") == "ground.medevac"


def test_target_agent_unknown_raises():
    with pytest.raises(ValueError):
        firefighter.target_agent_for_fleet("ufo")


def test_format_ack_accepted():
    out = firefighter.format_ack(
        {"accepted": True, "instance_id": "h-1", "eta_seconds": 5.0, "reason": None}
    )
    assert "accepted=True" in out
    assert "instance_id=h-1" in out
    assert "eta=5.0s" in out
    assert "reason=None" in out


def test_format_ack_rejected():
    out = firefighter.format_ack(
        {"accepted": False, "instance_id": None, "eta_seconds": None, "reason": "busy"}
    )
    assert "accepted=False" in out
    assert "reason=busy" in out


def test_grammar_constant_present_and_helpful():
    assert hasattr(firefighter, "GRAMMAR")
    text = firefighter.GRAMMAR.lower()
    # Mentions all three fleets and all three priority literals.
    for needle in ("heli", "ffunit", "medevac", "low", "med", "high"):
        assert needle in text, f"GRAMMAR should mention {needle!r}"


# ---------------------------------------------------------------------------
# Task 1: source-text negative gates (D-30 plain caller, D-32 Phase 3 deferral)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "needle, reason",
    [
        ("@mesh.agent(",     "plain caller, no decorator (D-30)"),
        ("AgentSpec(",       "plain caller does not register an agent (D-30)"),
        ("subject_source(",  "no sources on a plain caller"),
        ("kv_source(",       "no sources on a plain caller"),
        ("mesh.briefing",    "Phase 3 deferral (D-32)"),
        ("ThermalGrid",      "dropped artefact (post pure-KV-grid pivot)"),
        ("FireSpawn",        "dropped artefact"),
        ("FireSuppress",     "dropped artefact"),
        ("mesh.environment.thermal", "dropped artefact"),
        ("mesh.fire.spawn",  "dropped artefact"),
        ("mesh.fire.suppress", "dropped artefact"),
    ],
)
def test_firefighter_module_does_not_reference_forbidden(needle: str, reason: str):
    text = _FIREFIGHTER_PATH.read_text()
    assert needle not in text, f"{needle!r} must not appear in firefighter.py: {reason}"


@pytest.mark.parametrize("needle", ["bucket=", "prefix=", "model="])
def test_firefighter_module_does_not_use_aspirational_kwargs(needle: str):
    """A-09: the real SDK has no bucket=/prefix=/model= kwargs."""
    text = _FIREFIGHTER_PATH.read_text()
    # Strip pure-comment lines to allow the negative gate documentation.
    code_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    code_text = "\n".join(code_lines)
    assert needle not in code_text, f"{needle!r} is not a real SDK kwarg (A-09)"


def test_firefighter_module_wires_the_nl_tasker_path():
    """Phase 3 (D-32): the --nl default routes non-grammar lines through
    mesh.call("tasker", ...) and audits raw intent on mesh.fire.*.intent."""
    text = _FIREFIGHTER_PATH.read_text()
    assert 'mesh.call(\n            "tasker"' in text or '"tasker"' in text
    assert "TaskTranslateRequest" in text
    assert "FirefighterIntent" in text
    assert ".intent" in text


# ---------------------------------------------------------------------------
# Task 2: live REPL against AgentMesh.local() with stub responder fleets.
# ---------------------------------------------------------------------------

from openagentmesh import AgentMesh  # noqa: E402
from openagentmesh._models import AgentSpec  # noqa: E402


async def _make_mesh_with_stubs(
    *,
    heli_ack: DispatchAck | None = None,
    ffunit_ack: DispatchAck | None = None,
    medevac_ack: DispatchAck | None = None,
):
    """Helper: build an embedded mesh with three stub responders that mirror
    the real fleet agent names (low-alt.heli / ground.ffunit / ground.medevac).

    Returned as an async-context-manager so callers ``async with`` it.
    """
    heli_ack = heli_ack or DispatchAck(accepted=True, instance_id="h-stub", eta_seconds=5.0)
    ffunit_ack = ffunit_ack or DispatchAck(accepted=True, instance_id="f-stub", eta_seconds=10.0)
    medevac_ack = medevac_ack or DispatchAck(accepted=True, instance_id="m-stub", eta_seconds=7.5)

    mesh = AgentMesh()

    @mesh.agent(AgentSpec(name="low-alt.heli", description="stub heli responder"))
    async def heli_stub(order: DispatchOrder) -> DispatchAck:
        return heli_ack

    @mesh.agent(AgentSpec(name="ground.ffunit", description="stub ffunit responder"))
    async def ffunit_stub(order: DispatchOrder) -> DispatchAck:
        return ffunit_ack

    @mesh.agent(AgentSpec(name="ground.medevac", description="stub medevac responder"))
    async def medevac_stub(order: DispatchOrder) -> DispatchAck:
        return medevac_ack

    return mesh


async def test_repl_dispatches_to_heli_via_stub():
    mesh = await _make_mesh_with_stubs()
    async with mesh.local():
        in_stream = io.StringIO("heli 0 0 med\n")
        out_stream = io.StringIO()
        err_stream = io.StringIO()
        await firefighter.repl(
            mesh,
            operator_id="op-test",
            in_stream=in_stream,
            out_stream=out_stream,
            err_stream=err_stream,
        )
        out = out_stream.getvalue()
        assert "accepted=True" in out
        assert "instance_id=h-stub" in out


async def test_repl_dispatches_to_ffunit_and_medevac_via_stubs():
    mesh = await _make_mesh_with_stubs()
    async with mesh.local():
        in_stream = io.StringIO("ffunit 1 1 high\nmedevac 0 0 high 2\n")
        out_stream = io.StringIO()
        err_stream = io.StringIO()
        await firefighter.repl(
            mesh,
            operator_id="op-test",
            in_stream=in_stream,
            out_stream=out_stream,
            err_stream=err_stream,
        )
        out = out_stream.getvalue()
        assert "instance_id=f-stub" in out
        assert "instance_id=m-stub" in out


async def test_repl_handles_bad_input_without_exit():
    mesh = await _make_mesh_with_stubs()
    async with mesh.local():
        in_stream = io.StringIO("garbage\nheli 0 0 high\n")
        out_stream = io.StringIO()
        err_stream = io.StringIO()
        await firefighter.repl(
            mesh,
            operator_id="op-test",
            in_stream=in_stream,
            out_stream=out_stream,
            err_stream=err_stream,
            nl=False,  # typed-grammar mode: non-grammar lines are errors
        )
        err = err_stream.getvalue()
        out = out_stream.getvalue()
        assert "error" in err.lower(), f"expected error on stderr, got {err!r}"
        assert out.count("accepted=True") == 1, (
            "exactly one successful dispatch should appear after the bad line"
        )


async def test_repl_help_prints_grammar():
    mesh = await _make_mesh_with_stubs()
    async with mesh.local():
        in_stream = io.StringIO("help\nheli 0 0 high\n")
        out_stream = io.StringIO()
        err_stream = io.StringIO()
        await firefighter.repl(
            mesh,
            operator_id="op-test",
            in_stream=in_stream,
            out_stream=out_stream,
            err_stream=err_stream,
        )
        out = out_stream.getvalue()
        # First line of GRAMMAR should appear in stdout when 'help' is typed.
        # The grammar must contain at least one fleet keyword to be useful.
        assert "heli" in out
        assert "accepted=True" in out


async def test_repl_nl_line_translates_and_dispatches_with_auto_accept():
    """D-32 NL path: sentence -> stub tasker -> TaskCommand -> heli dispatch."""
    mesh = await _make_mesh_with_stubs()

    @mesh.agent(AgentSpec(name="tasker", description="stub NL translator"))
    async def tasker_stub(req: TaskTranslateRequest) -> TaskCommand:
        assert "water bomber" in req.text
        return TaskCommand(
            target_fleet="heli",
            coords=Coords(x=1.0, y=-2.0),
            incident_id=None,
            priority="high",
            persons_estimated=0,
            rationale="operator asked for the heli",
        )

    async with mesh.local():
        in_stream = io.StringIO("send the water bomber to the fire\n")
        out_stream = io.StringIO()
        err_stream = io.StringIO()
        await firefighter.repl(
            mesh,
            operator_id="op-test",
            in_stream=in_stream,
            out_stream=out_stream,
            err_stream=err_stream,
            auto_accept=True,
        )
        out = out_stream.getvalue()
        assert "tasker:" in out
        assert "rationale: operator asked for the heli" in out
        assert "instance_id=h-stub" in out, "translated command must reach the heli stub"


async def test_repl_nl_confirmation_no_cancels_dispatch():
    mesh = await _make_mesh_with_stubs()

    @mesh.agent(AgentSpec(name="tasker", description="stub NL translator"))
    async def tasker_stub(req: TaskTranslateRequest) -> TaskCommand:
        return TaskCommand(
            target_fleet="ffunit",
            coords=Coords(x=0.0, y=0.0),
            incident_id=None,
            priority="low",
            persons_estimated=0,
            rationale="r",
        )

    async with mesh.local():
        in_stream = io.StringIO("do the thing\nn\n")
        out_stream = io.StringIO()
        err_stream = io.StringIO()
        await firefighter.repl(
            mesh,
            operator_id="op-test",
            in_stream=in_stream,
            out_stream=out_stream,
            err_stream=err_stream,
        )
        out = out_stream.getvalue()
        assert "cancelled" in out
        assert "accepted=" not in out, "no dispatch after a declined confirmation"


async def test_repl_empty_or_eof_exits_cleanly():
    mesh = await _make_mesh_with_stubs()
    async with mesh.local():
        in_stream = io.StringIO("")
        out_stream = io.StringIO()
        err_stream = io.StringIO()
        # Must return without raising; no dispatch should happen.
        await firefighter.repl(
            mesh,
            operator_id="op-test",
            in_stream=in_stream,
            out_stream=out_stream,
            err_stream=err_stream,
        )
        assert "accepted" not in out_stream.getvalue()


def test_main_callable_and_exposes_argv_signature():
    assert callable(firefighter.main)
    # Signature: main(argv: list[str]) -> int
    import inspect

    sig = inspect.signature(firefighter.main)
    assert len(sig.parameters) == 1
