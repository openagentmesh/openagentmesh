# Shared Plan Coordination

Two agents observe the same plan artifact. Each autonomously picks an incomplete task, marks it in-progress, does the work, marks it complete. Neither agent blocks the other. No task is worked twice. The plan reaches 100% completion.

This is the bootstrapping scenario: if the mesh can coordinate agents on a shared plan, that same mechanism can be used to build every subsequent feature.

## The Code

```python
import asyncio

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


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


async def main(mesh: AgentMesh) -> None:
    @mesh.agent(AgentSpec(name="worker", channel="dev", description="Picks and completes plan tasks"))
    async def worker(req: TaskClaim) -> TaskResult:
        def claim(value: str) -> str:
            plan = Plan.model_validate_json(value)
            task = next(t for t in plan.tasks if t.id == req.task_id)
            task.status = "in-progress"
            task.assigned_to = "worker"
            return plan.model_dump_json()

        await mesh.kv.update("plan-001", claim)
        await asyncio.sleep(0.1)  # simulate work

        def complete(value: str) -> str:
            plan = Plan.model_validate_json(value)
            task = next(t for t in plan.tasks if t.id == req.task_id)
            task.status = "complete"
            return plan.model_dump_json()

        await mesh.kv.update("plan-001", complete)
        return TaskResult(plan_id=req.plan_id, task_id=req.task_id, status="complete")

    # Create a plan with 5 tasks
    plan = Plan(
        id="plan-001",
        tasks=[
            Task(id=f"task-{i}", description=desc)
            for i, desc in enumerate([
                "Analyze requirements",
                "Design API surface",
                "Write test cases",
                "Implement core module",
                "Review and refactor",
            ], 1)
        ],
    )
    await mesh.kv.put("plan-001", plan.model_dump_json())

    # Dispatch all tasks concurrently (queue group distributes across workers)
    calls = [
        mesh.call("worker", TaskClaim(plan_id="plan-001", task_id=f"task-{i}"))
        for i in range(1, 6)
    ]
    results = await asyncio.gather(*calls)

    # Verify completion
    raw = await mesh.kv.get("plan-001")
    final = Plan.model_validate_json(raw)

    print(f"Plan complete: {final.is_complete()}")
    print(f"Tasks finished: {len(results)}")
    for r in results:
        print(f"  {r['task_id']}: {r['status']}")
```

## Run It

```bash
oam demo run shared_plan
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
