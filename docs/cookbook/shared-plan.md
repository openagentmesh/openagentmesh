# Shared Plan Coordination

Two agents observe the same plan artifact. Each autonomously picks an incomplete task, marks it in-progress, does the work, marks it complete. Neither agent blocks the other. No task is worked twice. The plan reaches 100% completion.

This is the bootstrapping scenario: if the mesh can coordinate agents on a shared plan, that same mechanism can be used to build every subsequent feature.

## The Code

```python
--8<-- "src/openagentmesh/demos/shared_plan.py"
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
