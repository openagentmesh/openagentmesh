"""Hierarchical-spawn baseline: one orchestrator, throwaway workers.

The Claude-Code-subagents shape expressed as mesh calls: the orchestrator
holds all context, calls one worker per role lens, and merges. Workers get
the task in the request and never see each other's output — no lateral
edges, no blackboard. Same model and same role lenses as the standing team,
so the topology is the only variable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from openagentmesh import AgentSpec, Usage, report_usage

from .llm import SYNTHESIZE_MARKER, ChatModel, parse_decision
from .personas import PERSONAS, Persona
from .records import Decision, TaskBrief

if TYPE_CHECKING:
    from openagentmesh import AgentMesh

ORCHESTRATOR = "hier.orchestrator"

_ORCHESTRATOR_SYSTEM = (
    "You are the orchestrator of a hierarchical agent team. You delegated a "
    "design question to role-lens workers and now hold all their analyses. "
    "Merge them into one decision."
)


class WorkRequest(BaseModel):
    task_id: str
    question: str
    context: str = ""


class WorkReply(BaseModel):
    persona: str
    analysis: str


def _worker_name(persona: Persona) -> str:
    return f"hier.worker.{persona.key}"


def _worker_prompt(req: WorkRequest) -> str:
    return (
        f"Design question: {req.question}\n\nContext: {req.context}\n\n"
        "Analyze this question through your lens and give your recommendation "
        "with rationale."
    )


def _merge_prompt(task: TaskBrief, analyses: list[WorkReply]) -> str:
    block = "\n\n".join(f"[{a.persona}]\n{a.analysis}" for a in analyses)
    return (
        f"Design question: {task.question}\n\nContext: {task.context}\n\n"
        f"Worker analyses:\n{block}\n\n"
        f"Merge these into the final decision. {SYNTHESIZE_MARKER} with keys "
        '"recommendation" (string), "alternatives" (list of strings), '
        '"risks" (list of strings), "rationale" (string).'
    )


def register_hierarchy(
    mesh: AgentMesh, model: ChatModel, personas: list[Persona] | None = None
) -> None:
    team = personas or PERSONAS

    for persona in team:
        if _worker_name(persona) in mesh._agents:
            continue

        def _make(p: Persona):
            async def work(req: WorkRequest) -> WorkReply:
                reply = await model.complete(p.system, _worker_prompt(req))
                report_usage(Usage(
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                    model=reply.model,
                ))
                return WorkReply(persona=p.name, analysis=reply.text)

            return work

        mesh.agent(AgentSpec(
            name=_worker_name(persona),
            description=f"Ephemeral {persona.display} worker for the hierarchical baseline.",
        ))(_make(persona))

    if ORCHESTRATOR not in mesh._agents:

        @mesh.agent(AgentSpec(
            name=ORCHESTRATOR,
            description="Decomposes a design question to role workers and merges the answers.",
        ))
        async def orchestrate(task: TaskBrief) -> Decision:
            analyses = []
            for persona in team:  # sequential: the parent mediates everything
                raw = await mesh.call(_worker_name(persona), WorkRequest(
                    task_id=task.task_id, question=task.question, context=task.context
                ))
                analyses.append(WorkReply.model_validate(raw))

            reply = await model.complete(
                _ORCHESTRATOR_SYSTEM, _merge_prompt(task, analyses)
            )
            report_usage(Usage(
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                model=reply.model,
            ))
            return parse_decision(reply.text, task.task_id, ORCHESTRATOR, False)


async def run_hierarchical(
    mesh: AgentMesh,
    model: ChatModel,
    task: TaskBrief,
    *,
    personas: list[Persona] | None = None,
    timeout: float = 300.0,
) -> Decision:
    """Run the baseline once; returns the orchestrator's merged decision."""
    register_hierarchy(mesh, model, personas)
    result = await mesh.call(ORCHESTRATOR, task, timeout=timeout)
    return Decision.model_validate(result)
