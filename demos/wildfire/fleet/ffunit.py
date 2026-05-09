"""ground.ffunit: Responder agent (boot + register + heartbeat only this phase, D-08, SCN-06).

The ffunit is an action-fleet Responder whose ``DispatchOrder -> DispatchAck``
handler exists for catalog correctness (so the admin UI sandbox in Phase 3
can introspect the contract) but is never called this phase. Phase 2 wires
the operator -> tasker -> dispatch path; until then the stub returns
``DispatchAck(accepted=False, reason="phase 1 stub: ...")``.

Phase 1 responsibilities (per D-08, D-11):

- Register catalog entry under name ``ground.ffunit`` so the admin UI
  registry shows the row.
- Run the shared 1 Hz heartbeat to ``wildfire.fleet.ground.ffunit.{instance_id}``
  so the admin UI's reader-side staleness check (D-10) flips the row to
  "live" within ~3 s.
- Stay at HQ (D-11). The ffunit does not move in Phase 1; the dispatch path
  that would move it is not exercised.

Phase 1 explicitly excludes (per D-08, A-05, A-08):

- No outbound pubsub (no FFUnitStatus emission this phase).
- No subject-driven or KV-watch sources.
- No throwaway test caller.

Three instances spawned by the orchestrator (FFUNIT_COUNT=3) share the
queue group ``q.ground.ffunit`` automatically per
``src/openagentmesh/_mesh.py:_subscribe_agent`` so first-available-wins
queue semantics are preserved for free when Phase 2 wires the dispatch.
Each instance writes its own heartbeat key
(``wildfire.fleet.ground.ffunit.{instance_id}``) so the admin UI shows
3 distinct live rows, even though they share one catalog entry.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os

from demos.wildfire.core.config import HQ
from demos.wildfire.core.contracts import DispatchAck, DispatchOrder
from demos.wildfire.core.heartbeat import heartbeat_loop
from openagentmesh import AgentMesh
from openagentmesh._models import AgentSpec

_log = logging.getLogger("wildfire.ffunit")


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------


def build_agent(mesh: AgentMesh) -> None:
    """Register the ground.ffunit Responder agent on ``mesh``.

    Phase 1: the handler is bound to keep the catalog correct (so the
    admin UI's invocation sandbox in Phase 3 can introspect the
    DispatchOrder / DispatchAck schemas). It is not invoked this phase
    (D-08); a Phase 2 caller will replace the stub body.
    """

    @mesh.agent(
        AgentSpec(
            name="ground.ffunit",
            description=(
                "Ground firefighter unit. Accepts DispatchOrder, simulates "
                "suppression, returns DispatchAck. (Phase 1: boot+heartbeat "
                "only; handler stub.)"
            ),
        ),
    )
    async def ffunit(order: DispatchOrder) -> DispatchAck:
        # Phase 1: never called per D-08. The stub returns a structured
        # rejection so any rogue caller surfaces loud rather than silently
        # appearing to succeed.
        return DispatchAck(
            accepted=False,
            instance_id=mesh.instance_id,
            eta_seconds=None,
            reason="phase 1 stub: ffunit not yet operational",
        )


# ---------------------------------------------------------------------------
# Process entry point: `python -m demos.wildfire.fleet.ffunit`
# ---------------------------------------------------------------------------


async def _main() -> None:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    mesh = AgentMesh(url)
    build_agent(mesh)

    async with mesh:
        hb = asyncio.create_task(
            heartbeat_loop(
                mesh,
                zone="ground",
                fleet_type="ffunit",
                get_state=lambda: "free",
                get_coords=lambda: HQ,
                get_assignment=lambda: None,
            )
        )
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            hb.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await hb


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
