"""``python -m demos.wildfire`` -- one-command demo boot.

Phase 5 reproducibility (DEMO_SCRIPT.md): ``--seed N`` pins the procedural
terrain (exported to children as ``WILDFIRE_SEED``), and every boot starts
from a clean slate by default -- the previous run's JetStream store is
wiped so no stale fires, registrations, or heartbeats replay into the
recording. ``--keep-state`` opts out for debugging continuity.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .core.config import WILDFIRE_SEED_DEFAULT
from .core.orchestrator import Orchestrator


def main(argv: list[str] | None = None) -> int:
    """Run the orchestrator. Returns its exit code (0 on clean Ctrl+C)."""
    parser = argparse.ArgumentParser(prog="demos.wildfire")
    parser.add_argument(
        "--seed",
        type=int,
        default=WILDFIRE_SEED_DEFAULT,
        help=f"World seed for reproducible terrain (default: {WILDFIRE_SEED_DEFAULT}).",
    )
    parser.add_argument(
        "--keep-state",
        action="store_true",
        help="Keep the previous run's JetStream store (default: wipe for a clean-slate demo boot).",
    )
    args = parser.parse_args(argv)

    try:
        return asyncio.run(
            Orchestrator(seed=args.seed, fresh=not args.keep_state).run()
        )
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
