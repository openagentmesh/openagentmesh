"""Metered experiment runner: one topology run -> one RunReport.

Measurements ride shipped primitives, nothing bespoke:
- token cost: ADR-0023 ``usage_reported`` observe events, tailed via
  ``mesh.observe.logs()`` and summed per agent;
- coordination traffic: a wiretap counting messages on ``mesh.agent.>``
  (requests to agents — the topology's mesh calls);
- wall time: monotonic clock around the run.

Numbers from StubModel runs are synthetic (machinery checks only); only
OpenRouterModel runs produce reportable experiment results.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from .hierarchical import run_hierarchical
from .llm import ChatModel
from .personas import PERSONAS, Persona
from .records import Decision, TaskBrief
from .standing_team import run_standing_team

if TYPE_CHECKING:
    from openagentmesh import AgentMesh

Topology = Literal["standing", "hierarchical"]


class AgentUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None
    events: int = 0


class RunReport(BaseModel):
    """Everything measured in one topology run, JSON-serializable."""

    topology: Topology
    task_id: str
    model: str | None = None
    wall_time_s: float
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float | None = None
    usage_by_agent: dict[str, AgentUsage] = Field(default_factory=dict)
    usage_event_count: int = 0
    message_count: int = 0
    decision: Decision | None = None
    synthetic: bool = False  # True for stub runs: numbers are NOT results


async def run_experiment(
    mesh: AgentMesh,
    model: ChatModel,
    topology: Topology,
    task: TaskBrief,
    *,
    personas: list[Persona] | None = None,
    rounds: int = 3,
    seed: int | None = None,
) -> RunReport:
    """Run one topology once with metering attached; return the report."""
    team = personas or PERSONAS
    usage_events: list = []
    message_count = 0

    async def _count(msg) -> None:
        nonlocal message_count
        message_count += 1

    # Raw subscription, not mesh.subscribe(): the wiretap must never decode
    # payloads (error envelopes would raise out of the iterator).
    tap = await mesh._conn.subscribe("mesh.agent.>", cb=_count)

    async def _tail_usage() -> None:
        async for event in mesh.observe.logs():
            if event.event == "usage_reported":
                usage_events.append(event)

    tail_task = asyncio.create_task(_tail_usage())
    await mesh._conn.flush()

    started = time.monotonic()
    try:
        if topology == "standing":
            decision = await run_standing_team(
                mesh, model, task, personas=team, rounds=rounds, seed=seed
            )
        else:
            decision = await run_hierarchical(mesh, model, task, personas=team)
        wall_time = time.monotonic() - started

        # Usage events arrive async; wait until the stream goes quiet.
        deadline = time.monotonic() + 3.0
        seen = -1
        while time.monotonic() < deadline and len(usage_events) != seen:
            seen = len(usage_events)
            await asyncio.sleep(0.15)
    finally:
        tail_task.cancel()
        await asyncio.gather(tail_task, return_exceptions=True)
        await tap.unsubscribe()

    by_agent: dict[str, AgentUsage] = {}
    for event in usage_events:
        agent = by_agent.setdefault(event.agent, AgentUsage())
        agent.input_tokens += event.data.get("input_tokens") or 0
        agent.output_tokens += event.data.get("output_tokens") or 0
        cost = event.data.get("estimated_cost_usd")
        if cost is not None:
            agent.estimated_cost_usd = (agent.estimated_cost_usd or 0.0) + cost
        agent.events += 1

    costs = [u.estimated_cost_usd for u in by_agent.values() if u.estimated_cost_usd]
    reply_model = getattr(model, "_slug", None)
    return RunReport(
        topology=topology,
        task_id=task.task_id,
        model=reply_model or ("stub" if type(model).__name__ == "StubModel" else None),
        wall_time_s=wall_time,
        total_input_tokens=sum(u.input_tokens for u in by_agent.values()),
        total_output_tokens=sum(u.output_tokens for u in by_agent.values()),
        estimated_cost_usd=sum(costs) if costs else None,
        usage_by_agent=by_agent,
        usage_event_count=len(usage_events),
        message_count=message_count,
        decision=decision,
        synthetic=type(model).__name__ == "StubModel",
    )
