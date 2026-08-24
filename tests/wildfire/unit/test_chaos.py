"""Phase 4 chaos-kill path: listener, dashboard publish, briefer reclaim."""

from __future__ import annotations

import asyncio
import time

import pytest

from demos.wildfire.core.chaos import chaos_kill_listener, chaos_kill_subject
from demos.wildfire.core.config import STALE_ASSIGNMENT_AFTER_S
from demos.wildfire.core.contracts import (
    ChaosKill,
    Coords,
    DetectionRecord,
    FleetMemberState,
)
from demos.wildfire.core.keys import detection_key, fleet_key
from demos.wildfire.dashboard.server import handle_chaos_kill
from demos.wildfire.fleet.briefer import reclaim_stale_assignments
from openagentmesh import AgentMesh


def _detection(detection_id: str, state: str, *, now: float) -> DetectionRecord:
    return DetectionRecord(
        detection_id=detection_id,
        state=state,
        coords=Coords(x=1.0, y=1.0),
        severity=0.6,
        detector_instance_id="uav-test",
        created_at=now,
        last_updated=now,
    )


def _member(instance_id: str, *, last_updated: float) -> FleetMemberState:
    return FleetMemberState(
        instance_id=instance_id,
        zone="low-alt",
        fleet_type="drone",
        coords=Coords(x=0.0, y=0.0),
        state="busy",
        current_assignment="d-1",
        last_updated=last_updated,
    )


class TestChaosKillListener:
    async def test_kill_frame_triggers_exit(self):
        async with AgentMesh.local() as mesh:
            exited: list[int] = []
            fired = asyncio.Event()

            def fake_exit(code: int) -> None:
                exited.append(code)
                fired.set()
                raise asyncio.CancelledError

            task = asyncio.create_task(chaos_kill_listener(mesh, _exit=fake_exit))
            await asyncio.sleep(0.2)  # listener subscription settles

            await mesh.publish(
                chaos_kill_subject(mesh.instance_id),
                ChaosKill(target_instance_id=mesh.instance_id),
            )
            await asyncio.wait_for(fired.wait(), timeout=3)
            assert exited == [1]
            task.cancel()

    async def test_other_instances_kill_is_ignored(self):
        async with AgentMesh.local() as mesh:
            exited: list[int] = []
            task = asyncio.create_task(
                chaos_kill_listener(mesh, _exit=lambda c: exited.append(c))
            )
            await asyncio.sleep(0.2)
            await mesh.publish(
                chaos_kill_subject("someone-else"),
                ChaosKill(target_instance_id="someone-else"),
            )
            await asyncio.sleep(0.3)
            assert exited == []
            task.cancel()


class TestDashboardChaosKill:
    async def test_publishes_chaos_kill_on_target_subject(self):
        async with AgentMesh.local() as mesh:
            got: asyncio.Queue[dict] = asyncio.Queue()

            async def _collect():
                async for frame in mesh.subscribe(subject="mesh.chaos.kill.>"):
                    await got.put(frame)

            collector = asyncio.create_task(_collect())
            await asyncio.sleep(0.2)

            await handle_chaos_kill(mesh, instance_id="drone-abc")
            frame = await asyncio.wait_for(got.get(), timeout=3)
            assert frame["target_instance_id"] == "drone-abc"
            collector.cancel()


class TestReclaimStaleAssignments:
    async def test_dead_drone_assignment_returns_to_pending(self):
        async with AgentMesh.local() as mesh:
            now = time.time()
            # Dead drone: heartbeat record far past the staleness cutoff.
            await mesh.kv.put_model(
                fleet_key("low-alt", "drone", "dead-drone"),
                _member("dead-drone", last_updated=now - STALE_ASSIGNMENT_AFTER_S - 5),
            )
            await mesh.kv.put_model(
                detection_key("d-dead"), _detection("d-dead", "assigned:dead-drone", now=now)
            )

            reclaimed = await reclaim_stale_assignments(mesh, now)

            assert reclaimed == ["d-dead"]
            rec = await mesh.kv.get_model(detection_key("d-dead"), DetectionRecord)
            assert rec.state == "pending"

    async def test_live_drone_assignment_untouched(self):
        async with AgentMesh.local() as mesh:
            now = time.time()
            await mesh.kv.put_model(
                fleet_key("low-alt", "drone", "live-drone"),
                _member("live-drone", last_updated=now),
            )
            await mesh.kv.put_model(
                detection_key("d-live"), _detection("d-live", "assigned:live-drone", now=now)
            )

            reclaimed = await reclaim_stale_assignments(mesh, now)

            assert reclaimed == []
            rec = await mesh.kv.get_model(detection_key("d-live"), DetectionRecord)
            assert rec.state == "assigned:live-drone"

    async def test_missing_fleet_record_counts_as_dead(self):
        async with AgentMesh.local() as mesh:
            now = time.time()
            await mesh.kv.put_model(
                detection_key("d-ghost"), _detection("d-ghost", "assigned:ghost", now=now)
            )

            reclaimed = await reclaim_stale_assignments(mesh, now)

            assert reclaimed == ["d-ghost"]

    async def test_pending_and_surveyed_ignored(self):
        async with AgentMesh.local() as mesh:
            now = time.time()
            await mesh.kv.put_model(
                detection_key("d-p"), _detection("d-p", "pending", now=now)
            )
            await mesh.kv.put_model(
                detection_key("d-s"), _detection("d-s", "surveyed", now=now)
            )

            reclaimed = await reclaim_stale_assignments(mesh, now)

            assert reclaimed == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
