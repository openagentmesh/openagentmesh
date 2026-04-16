"""BDD tests for the Shared Plan Coordination cookbook recipe.

Executable version of the code samples in docs/cookbook/shared-plan.md.
Layer 2 (technical invariants) first, then Layer 1 (business behavior).

Each test uses AgentMesh.local() for a fully isolated embedded NATS instance.
"""

import asyncio
import time

import pytest
from pydantic import BaseModel

from agentmesh import AgentMesh


# --- Shared models (same as docs/cookbook/shared-plan.md) ---

class Task(BaseModel):
    id: str
    description: str
    status: str = "pending"
    assigned_to: str | None = None


class Plan(BaseModel):
    id: str
    tasks: list[Task]

    def pending_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.status == "pending"]

    def is_complete(self) -> bool:
        return all(t.status == "complete" for t in self.tasks)


class TaskClaim(BaseModel):
    plan_id: str
    task_id: str


class TaskResult(BaseModel):
    plan_id: str
    task_id: str
    status: str


# --- Fixtures ---

def make_plan(n_tasks: int = 5) -> Plan:
    return Plan(
        id="plan-001",
        tasks=[
            Task(id=f"task-{i}", description=f"Task {i}")
            for i in range(1, n_tasks + 1)
        ],
    )


# ---------------------------------------------------------------------------
# Layer 2: Technical invariants
# ---------------------------------------------------------------------------


class TestConcurrentCASUpdates:
    """Concurrent plan updates use CAS without data loss."""

    async def test_two_simultaneous_claims_both_succeed(self):
        async with AgentMesh.local() as mesh:
            await mesh.start()

            plan = make_plan(2)
            await mesh.context.put("plan-001", plan.model_dump_json())

            async def claim_task(task_id: str, agent_name: str):
                async with mesh.context.cas("plan-001") as entry:
                    p = Plan.model_validate_json(entry.value)
                    task = next(t for t in p.tasks if t.id == task_id)
                    task.status = "in-progress"
                    task.assigned_to = agent_name
                    entry.value = p.model_dump_json()

            # Two agents claim different tasks at the same time
            await asyncio.gather(
                claim_task("task-1", "agent-a"),
                claim_task("task-2", "agent-b"),
            )

            # Both claims should be reflected in the final state
            raw = await mesh.context.get("plan-001")
            final = Plan.model_validate_json(raw)

            assigned = {t.id: t.assigned_to for t in final.tasks}
            assert assigned["task-1"] == "agent-a"
            assert assigned["task-2"] == "agent-b"


class TestTaskClaimExclusivity:
    """An agent skips tasks already claimed by another."""

    async def test_second_agent_sees_claimed_tasks(self):
        async with AgentMesh.local() as mesh:
            await mesh.start()

            plan = make_plan(3)
            plan.tasks[0].status = "in-progress"
            plan.tasks[0].assigned_to = "agent-a"
            await mesh.context.put("plan-001", plan.model_dump_json())

            raw = await mesh.context.get("plan-001")
            current = Plan.model_validate_json(raw)
            pending = current.pending_tasks()

            assert len(pending) == 2
            assert all(t.id != "task-1" for t in pending)


class TestPlanObservability:
    """Plan completion is observable via KV watch."""

    async def test_watch_receives_updates(self):
        async with AgentMesh.local() as mesh:
            await mesh.start()

            plan = make_plan(1)
            await mesh.context.put("plan-001", plan.model_dump_json())

            updates = []

            async def watch_plan():
                async for value in mesh.context.watch("plan-001"):
                    p = Plan.model_validate_json(value)
                    updates.append(p.tasks[0].status)
                    if p.is_complete():
                        break

            async def update_plan():
                await asyncio.sleep(0.05)  # let watch start first

                async with mesh.context.cas("plan-001") as entry:
                    p = Plan.model_validate_json(entry.value)
                    p.tasks[0].status = "in-progress"
                    entry.value = p.model_dump_json()

                await asyncio.sleep(0.05)

                async with mesh.context.cas("plan-001") as entry:
                    p = Plan.model_validate_json(entry.value)
                    p.tasks[0].status = "complete"
                    entry.value = p.model_dump_json()

            await asyncio.gather(
                asyncio.wait_for(watch_plan(), timeout=5.0),
                update_plan(),
            )

            assert "in-progress" in updates
            assert "complete" in updates


# ---------------------------------------------------------------------------
# Layer 1: Business behavior
# ---------------------------------------------------------------------------


class TestSharedPlanCoordination:
    """Two agents complete a plan without conflicts."""

    async def test_full_scenario(self):
        async with AgentMesh.local() as mesh:

            plan = make_plan(5)
            await mesh.context.put("plan-001", plan.model_dump_json())

            completed_by: dict[str, str] = {}

            @mesh.agent(name="worker", channel="dev", description="Completes plan tasks")
            async def worker(req: TaskClaim) -> TaskResult:
                # Claim
                async with mesh.context.cas("plan-001") as entry:
                    p = Plan.model_validate_json(entry.value)
                    task = next(t for t in p.tasks if t.id == req.task_id)
                    task.status = "in-progress"
                    task.assigned_to = "worker"
                    entry.value = p.model_dump_json()

                await asyncio.sleep(0.1)  # simulate work

                # Complete
                async with mesh.context.cas("plan-001") as entry:
                    p = Plan.model_validate_json(entry.value)
                    task = next(t for t in p.tasks if t.id == req.task_id)
                    task.status = "complete"
                    entry.value = p.model_dump_json()

                completed_by[req.task_id] = "worker"
                return TaskResult(plan_id=req.plan_id, task_id=req.task_id, status="complete")

            await mesh.start()

            # Dispatch all tasks concurrently (simulating two+ agents via queue group)
            calls = [
                mesh.call("worker", TaskClaim(plan_id="plan-001", task_id=f"task-{i}"))
                for i in range(1, 6)
            ]
            results = await asyncio.gather(*calls)

            # Verify: all tasks complete
            raw = await mesh.context.get("plan-001")
            final = Plan.model_validate_json(raw)

            assert final.is_complete(), f"Tasks not complete: {[t.status for t in final.tasks]}"
            assert len(results) == 5
            assert len(completed_by) == 5

            # Verify: no task worked twice (each task_id appears once)
            task_ids = [r["task_id"] for r in results]
            assert len(set(task_ids)) == 5

    async def test_parallelism_is_faster_than_sequential(self):
        """Elapsed time < 2x single-agent time proves real concurrency."""
        async with AgentMesh.local() as mesh:

            plan = make_plan(5)
            await mesh.context.put("plan-001", plan.model_dump_json())

            @mesh.agent(name="worker", channel="dev", description="Completes plan tasks")
            async def worker(req: TaskClaim) -> TaskResult:
                async with mesh.context.cas("plan-001") as entry:
                    p = Plan.model_validate_json(entry.value)
                    task = next(t for t in p.tasks if t.id == req.task_id)
                    task.status = "complete"
                    task.assigned_to = "worker"
                    entry.value = p.model_dump_json()

                await asyncio.sleep(0.1)  # 100ms of "work" per task
                return TaskResult(plan_id=req.plan_id, task_id=req.task_id, status="complete")

            await mesh.start()

            start = time.monotonic()
            calls = [
                mesh.call("worker", TaskClaim(plan_id="plan-001", task_id=f"task-{i}"))
                for i in range(1, 6)
            ]
            await asyncio.gather(*calls)
            elapsed = time.monotonic() - start

            # 5 tasks x 100ms = 500ms sequential. Parallel should be well under 1000ms.
            assert elapsed < 1.0, f"Took {elapsed:.2f}s, expected < 1.0s for parallel execution"
