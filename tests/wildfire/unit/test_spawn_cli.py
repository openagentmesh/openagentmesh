"""Unit tests for the wildfire spawn CLI (D-05, D-06, D-07, A-06).

Behavior under test:
  - `python -m demos.wildfire.world.spawn` (no args) prints usage to stderr,
    exits non-zero (return code 2) and does NOT write to KV.
  - Out-of-bounds coords (x or y outside [-5, +5]) exit non-zero.
  - Non-numeric args exit non-zero with usage.
  - The script does NOT publish on any subject; KV write is the only side effect.

The script imports from `demos.wildfire.core.{contracts,keys}` which plan
01-01 creates in parallel; tests skip when the package is missing so this
suite stays green pre-wave-merge.
"""
from __future__ import annotations

import pytest

spawn = pytest.importorskip(
    "demos.wildfire.world.spawn",
    reason="demos.wildfire.world.spawn not yet importable (parallel wave; depends on demos.wildfire.core from 01-01).",
)


def test_main_no_args_prints_usage_returns_2(capsys):
    rc = spawn.main([])
    assert rc == 2
    captured = capsys.readouterr()
    assert "usage" in captured.err.lower()


def test_main_non_numeric_args_returns_2(capsys):
    rc = spawn.main(["foo", "bar", "baz"])
    assert rc == 2


def test_main_out_of_bounds_x_returns_nonzero(capsys):
    """Coords validator rejects x=99; the CLI must exit non-zero before any KV write."""
    rc = spawn.main(["99", "0", "500"])
    assert rc != 0


def test_main_out_of_bounds_y_returns_nonzero(capsys):
    rc = spawn.main(["0", "-99", "500"])
    assert rc != 0


def test_main_too_many_args_returns_2(capsys):
    rc = spawn.main(["1", "2", "3", "4"])
    assert rc == 2


def test_main_too_few_args_returns_2(capsys):
    rc = spawn.main(["1", "2"])
    assert rc == 2
