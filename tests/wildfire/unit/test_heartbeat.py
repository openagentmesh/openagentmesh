"""Unit tests for the shared fleet heartbeat coroutine (D-09, D-10, A-08).

The coroutine must:
  - be importable from `demos.wildfire.core.heartbeat`
  - be an async function (`inspect.iscoroutinefunction == True`)
  - write `FleetMemberState` to `wildfire.fleet.{zone}.{type}.{instance_id}`
    every `HEARTBEAT_INTERVAL_S` seconds via `mesh.kv.put_model`
  - exit cleanly on `asyncio.CancelledError` (no re-raise of the same heartbeat)
  - swallow per-iteration write failures (transient KV hiccups must not kill
    the fleet member's main work)

Note (parallel wave): the `demos.wildfire.core` package is created concurrently
by plan 01-01 in another worktree. Tests `pytest.skip` when those modules are
not yet importable so this suite stays green inside the 01-02 worktree before
the wave merge.
"""
from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

heartbeat = pytest.importorskip(
    "demos.wildfire.core.heartbeat",
    reason="demos.wildfire.core.heartbeat not yet on disk (parallel wave; plan 01-01 creates the package).",
)
contracts = pytest.importorskip("demos.wildfire.core.contracts")
keys = pytest.importorskip("demos.wildfire.core.keys")


def test_heartbeat_loop_is_async_function():
    assert inspect.iscoroutinefunction(heartbeat.heartbeat_loop)


def test_heartbeat_loop_signature_matches_plan():
    """Signature: (mesh, *, zone, fleet_type, get_state, get_coords,
    get_assignment=lambda:None, interval_s=HEARTBEAT_INTERVAL_S)."""
    sig = inspect.signature(heartbeat.heartbeat_loop)
    params = sig.parameters
    assert "mesh" in params
    assert params["mesh"].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    for kw in ("zone", "fleet_type", "get_state", "get_coords"):
        assert kw in params, f"missing keyword-only param: {kw}"
        assert params[kw].kind == inspect.Parameter.KEYWORD_ONLY, (
            f"{kw} must be keyword-only"
        )
    assert "get_assignment" in params
    assert params["get_assignment"].default is not inspect.Parameter.empty, (
        "get_assignment should have a default (lambda returning None)"
    )
    assert "interval_s" in params
    assert params["interval_s"].default is not inspect.Parameter.empty, (
        "interval_s should default to HEARTBEAT_INTERVAL_S"
    )


@pytest.mark.asyncio
async def test_heartbeat_loop_writes_fleet_member_state_each_tick():
    """Each iteration calls `mesh.kv.put_model(fleet_key(...), FleetMemberState(...))`."""
    Coords = contracts.Coords
    fake_mesh = SimpleNamespace(
        instance_id="test-instance-abc",
        kv=SimpleNamespace(put_model=AsyncMock(return_value=1)),
    )
    coords = Coords(x=0.0, y=0.0)

    task = asyncio.create_task(
        heartbeat.heartbeat_loop(
            fake_mesh,
            zone="low-alt",
            fleet_type="drone",
            get_state=lambda: "free",
            get_coords=lambda: coords,
            get_assignment=lambda: None,
            interval_s=0.01,
        ),
    )
    # Give the loop time to write at least once, then cancel.
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        # Either accept or convert; behavior is "exit cleanly". Both are fine
        # because asyncio.Task.cancel() always surfaces a CancelledError to the
        # awaiter unless the task already returned. The "no re-raise of the same
        # heartbeat" constraint applies to the body, not to task cancellation.
        pass

    assert fake_mesh.kv.put_model.await_count >= 1
    args, _ = fake_mesh.kv.put_model.await_args_list[0]
    key, record = args
    assert key == keys.fleet_key("low-alt", "drone", "test-instance-abc")
    assert isinstance(record, contracts.FleetMemberState)
    assert record.instance_id == "test-instance-abc"
    assert record.zone == "low-alt"
    assert record.fleet_type == "drone"
    assert record.state == "free"
    assert record.current_assignment is None


@pytest.mark.asyncio
async def test_heartbeat_loop_continues_on_put_failure():
    """A single put failure should be logged and swallowed -- the loop survives."""
    Coords = contracts.Coords

    call_count = {"n": 0}

    async def flaky_put_model(key, model):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient KV hiccup")
        return 1

    fake_mesh = SimpleNamespace(
        instance_id="abc",
        kv=SimpleNamespace(put_model=flaky_put_model),
    )
    coords = Coords(x=0.0, y=0.0)

    task = asyncio.create_task(
        heartbeat.heartbeat_loop(
            fake_mesh,
            zone="low-alt",
            fleet_type="drone",
            get_state=lambda: "free",
            get_coords=lambda: coords,
            interval_s=0.01,
        ),
    )
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # The first call raised; subsequent calls must have happened (loop survived).
    assert call_count["n"] >= 2, (
        f"expected the loop to continue after the first put failed, got {call_count['n']} calls"
    )
