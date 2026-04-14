"""Shared Plan Coordination: Expected DX

This is the DX contract. This is the code a library user would write to
coordinate two agents on a shared plan. If this looks awkward, the API
is wrong. Fix the API before touching implementation.

The mesh provides:
- AgentMesh.local() for embedded NATS with JetStream + KV
- mesh.context for shared KV state (plans, config, coordination data)
- CAS-based updates so concurrent agents don't clobber each other
- @mesh.agent decorator for reactive handlers
"""

import asyncio

from pydantic import BaseModel

from agentmesh import AgentMesh


# --- Models ---

class Task(BaseModel):
    id: str
    description: str
    status: str = "pending"  # pending | in-progress | complete
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
    status: str  # "complete"


# --- The user's code ---

async def main():
    async with AgentMesh.local() as mesh:

        # Store the initial plan in shared context
        plan = Plan(
            id="plan-001",
            tasks=[
                Task(id="task-1", description="Analyze requirements"),
                Task(id="task-2", description="Design API surface"),
                Task(id="task-3", description="Write test cases"),
                Task(id="task-4", description="Implement core module"),
                Task(id="task-5", description="Review and refactor"),
            ],
        )
        await mesh.context.put("plan-001", plan.model_dump_json())

        # Worker agent: claims a task, does work, marks complete.
        # Two instances run in the same queue group for load balancing.
        @mesh.agent(name="worker", channel="dev", description="Picks and completes plan tasks")
        async def worker(req: TaskClaim) -> TaskResult:
            # CAS loop: read plan, update task status, write back atomically
            async with mesh.context.cas("plan-001") as entry:
                current_plan = Plan.model_validate_json(entry.value)
                task = next(t for t in current_plan.tasks if t.id == req.task_id)
                task.status = "in-progress"
                task.assigned_to = "worker"
                entry.value = current_plan.model_dump_json()

            # Simulate doing actual work
            await asyncio.sleep(0.1)

            # Mark complete via another CAS update
            async with mesh.context.cas("plan-001") as entry:
                current_plan = Plan.model_validate_json(entry.value)
                task = next(t for t in current_plan.tasks if t.id == req.task_id)
                task.status = "complete"
                entry.value = current_plan.model_dump_json()

            return TaskResult(plan_id=req.plan_id, task_id=req.task_id, status="complete")

        # Coordinator: scans for pending tasks, dispatches to workers
        @mesh.agent(name="coordinator", channel="dev", description="Assigns plan tasks to workers")
        async def coordinator(req: Plan) -> Plan:
            while True:
                # Read current plan state
                raw = await mesh.context.get("plan-001")
                current_plan = Plan.model_validate_json(raw)

                pending = current_plan.pending_tasks()
                if not pending:
                    return current_plan  # All done

                # Dispatch pending tasks to workers concurrently
                calls = [
                    mesh.call("worker", TaskClaim(plan_id=current_plan.id, task_id=t.id))
                    for t in pending
                ]
                await asyncio.gather(*calls)

        await mesh.start()

        # Kick off coordination
        final_plan_data = await mesh.call("coordinator", plan)
        final_plan = Plan.model_validate(final_plan_data)

        assert final_plan.is_complete(), "Not all tasks completed"
        assert len({t.assigned_to for t in final_plan.tasks}) >= 1, "Work was distributed"

        print(f"Plan complete: {len(final_plan.tasks)} tasks done")


if __name__ == "__main__":
    asyncio.run(main())
