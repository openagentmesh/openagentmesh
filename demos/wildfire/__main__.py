"""``python -m demos.wildfire`` -- Phase 1 boot UX (D-01).

Parameterless. Configurability is added later (Phase 5 reproducibility harness,
D-07 -- ``--scenario path/to/scenario.json``). Phase 1 ships a single command
that brings up embedded NATS, the fleet, and the admin UI.
"""

from __future__ import annotations

import asyncio
import sys

from .core.orchestrator import Orchestrator


def main() -> int:
    """Run the orchestrator. Returns its exit code (0 on clean Ctrl+C)."""
    try:
        return asyncio.run(Orchestrator().run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
