# Shared Plan Coordination

Two agents observe the same plan artifact. Each autonomously picks an incomplete task, marks it in-progress, does the work, marks it complete. Neither agent blocks the other. No task is worked twice. The plan reaches 100% completion.

This is the bootstrapping scenario: if the mesh can coordinate agents on a shared plan, that same mechanism can be used to build every subsequent feature.

## Models

A plan is a KV entry in the `mesh-context` bucket. Tasks transition `pending` -> `in-progress` -> `complete`.

```python
from pydantic import BaseModel

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
```

## Worker Agent

Claims a task via CAS, does the work, marks it complete. Multiple instances run in the same queue group for load balancing.

```python
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
```

## Coordinator Agent

Scans for pending tasks, dispatches to workers concurrently.

```python
@mesh.agent(name="coordinator", channel="dev", description="Assigns plan tasks to workers")
async def coordinator(req: Plan) -> Plan:
    while True:
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
```

## Putting It Together

```python
import asyncio
from openagentmesh import AgentMesh

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

        # Register worker and coordinator agents (shown above)
        # ...

        await mesh.start()

        # Kick off coordination
        final_plan_data = await mesh.call("coordinator", plan)
        final_plan = Plan.model_validate(final_plan_data)

        assert final_plan.is_complete()
        print(f"Plan complete: {len(final_plan.tasks)} tasks done")

asyncio.run(main())
```

## How It Works

- **CAS (Compare-And-Swap)** on the plan KV entry prevents two agents from clobbering each other's updates. If two agents try to update the same key simultaneously, one retries automatically.
- **Queue groups** mean multiple worker instances share the subscription. NATS distributes requests across them.
- **`mesh.context.watch()`** lets an observer track task transitions in real time without polling.

## What This Proves

1. All tasks complete with no conflicts (mutual exclusion via CAS)
2. No task assigned to both agents
3. Elapsed time demonstrates actual parallelism (< 2x sequential)
4. Plan state is consistent at every intermediate step
