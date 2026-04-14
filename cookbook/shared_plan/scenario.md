# Scenario: Shared Plan Coordination

## Intent

Two agents observe the same plan artifact. Each autonomously picks an
incomplete task, marks it in-progress, does the work, marks it complete.
Neither agent blocks the other. No task is worked twice. The plan reaches
100% completion.

This is the bootstrapping scenario: if the mesh can coordinate agents on a
shared plan, that same mechanism can be used to build every subsequent feature.

## Behavior Layers

### Layer 1: Business behavior (BDD)

```gherkin
Feature: Shared plan coordination

  Scenario: Two agents complete a plan without conflicts
    Given a running mesh with JetStream
    And a plan stored in mesh context with 5 pending tasks
    And two worker agents registered on the mesh
    When both agents start processing the plan concurrently
    Then all 5 tasks reach "complete" status
    And no task is assigned to more than one agent
    And no exceptions are raised during execution
    And elapsed time is less than 2x single-agent time
```

### Layer 2: Technical invariants

```gherkin
  Scenario: Concurrent plan updates use CAS without data loss
    Given a plan stored as a KV entry
    When two agents attempt to claim different tasks simultaneously
    Then both claims succeed (possibly after CAS retries)
    And the plan contains both claims with no lost updates

  Scenario: An agent skips tasks already claimed by another
    Given a plan with one task already marked in-progress
    When a second agent scans for available tasks
    Then it selects only unclaimed tasks
    And does not duplicate work

  Scenario: Plan completion is observable
    Given a plan with tasks being worked
    When a consumer watches the plan KV key
    Then it receives updates as tasks transition states
    And can determine when all tasks are complete
```

## Given: Plan Data Structure

A plan is a KV entry in the `mesh-context` bucket. Structure:

```json
{
  "id": "plan-001",
  "tasks": [
    {"id": "task-1", "description": "Analyze requirements", "status": "pending", "assigned_to": null},
    {"id": "task-2", "description": "Design API surface", "status": "pending", "assigned_to": null},
    {"id": "task-3", "description": "Write test cases", "status": "pending", "assigned_to": null},
    {"id": "task-4", "description": "Implement core module", "status": "pending", "assigned_to": null},
    {"id": "task-5", "description": "Review and refactor", "status": "pending", "assigned_to": null}
  ]
}
```

Task status transitions: `pending` -> `in-progress` -> `complete`

## Success Criteria

1. All 5 tasks complete
2. No task assigned to both agents (mutual exclusion via CAS)
3. No exceptions raised
4. Elapsed time demonstrates actual parallelism (< 2x sequential)
5. Plan state is consistent at every intermediate step (no partial writes)
