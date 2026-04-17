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
from openagentmesh import AgentSpec

spec = AgentSpec(name="worker", channel="dev", description="Picks and completes plan tasks")

@mesh.agent(spec)
async def worker(req: TaskClaim) -> TaskResult:
    # CAS update: read plan, update task status, write back atomically
    def claim(value: str) -> str:
        plan = Plan.model_validate_json(value)
        task = next(t for t in plan.tasks if t.id == req.task_id)
        task.status = "in-progress"
        task.assigned_to = "worker"
        return plan.model_dump_json()

    await mesh.kv.update("plan-001", claim)

    # Simulate doing actual work
    await asyncio.sleep(0.1)

    # Mark complete via another CAS update
    def complete(value: str) -> str:
        plan = Plan.model_validate_json(value)
        task = next(t for t in plan.tasks if t.id == req.task_id)
        task.status = "complete"
        return plan.model_dump_json()

    await mesh.kv.update("plan-001", complete)

    return TaskResult(plan_id=req.plan_id, task_id=req.task_id, status="complete")
```

## Coordinator Agent

Scans for pending tasks, dispatches to workers concurrently.

```python
coord_spec = AgentSpec(name="coordinator", channel="dev", description="Assigns plan tasks to workers")

@mesh.agent(coord_spec)
async def coordinator(req: Plan) -> Plan:
    while True:
        raw = await mesh.kv.get("plan-001")
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
        await mesh.kv.put("plan-001", plan.model_dump_json())

        # Register worker and coordinator agents (shown above)
        # ...

        # Kick off coordination
        final_plan_data = await mesh.call("coordinator", plan)
        final_plan = Plan.model_validate(final_plan_data)

        assert final_plan.is_complete()
        print(f"Plan complete: {len(final_plan.tasks)} tasks done")

asyncio.run(main())
```

## How It Works

- **`kv.update(key, fn)`** uses compare-and-swap with automatic retry. The mutation function receives the current value and returns the new value. If another agent updated the key between the read and write, the function is called again with the fresh value.
- **Queue groups** mean multiple worker instances share the subscription. NATS distributes requests across them.
- **`mesh.kv.watch()`** lets an observer track task transitions in real time without polling.

## What This Proves

1. All tasks complete with no conflicts (mutual exclusion via CAS)
2. No task assigned to both agents
3. Elapsed time demonstrates actual parallelism (< 2x sequential)
4. Plan state is consistent at every intermediate step
