"""Pytest fixtures + path setup for the wildfire demo test suite.

The wildfire demo lives at `demos/` (sibling to `src/`), deliberately not
shipped in the published wheel (see D-02 in 01-CONTEXT.md, plan 01-01 Task 1).
Add the worktree root to sys.path so `from demos.wildfire.core...` resolves
under pytest the same way it resolves under `python -m demos.wildfire.<role>`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
