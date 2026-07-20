"""Standing-team topology: peers + blackboard + randomized round-robin turns.

No orchestrator holds content. Each persona is a mesh agent that reads the
blackboard, thinks with its own lens, and writes its position back. The
dispatcher below is a mechanical turn-granting tool (the brainstorm's
round-robin option 2): it carries no task content, only turn tokens —
randomized order, fixed round count, so storms and stalls are impossible
by construction.

Delphi-style rounds: independent position -> read peers -> revise ->
converge (stop early when a full round changes nothing materially).
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from openagentmesh import AgentSpec, Usage, report_usage

from .blackboard import Blackboard
from .llm import SYNTHESIZE_MARKER, ChatModel, parse_decision, split_reply
from .personas import PERSONAS, Persona
from .records import Decision, Position, TaskBrief, TurnRequest, TurnResult

if TYPE_CHECKING:
    from openagentmesh import AgentMesh


def _position_prompt(task: TaskBrief) -> str:
    return (
        f"Design question: {task.question}\n\nContext: {task.context}\n\n"
        "State your independent position. First line: your claim in one "
        "sentence. Then your rationale."
    )


def _revise_prompt(task: TaskBrief, own: Position | None, peers: list[Position]) -> str:
    peer_block = "\n\n".join(
        f"[{p.persona}] claim: {p.claim}\nrationale: {p.rationale}" for p in peers
    )
    own_block = f"claim: {own.claim}\nrationale: {own.rationale}" if own else "(none yet)"
    return (
        f"Design question: {task.question}\n\nContext: {task.context}\n\n"
        f"Your current position:\n{own_block}\n\n"
        f"Your peers' current positions:\n{peer_block}\n\n"
        "Revise your position in light of the peers' arguments. Keep your "
        "claim if nothing defeats it. First line: your (possibly unchanged) "
        "claim. Then your rationale."
    )


def _synthesize_prompt(task: TaskBrief, positions: list[Position]) -> str:
    block = "\n\n".join(
        f"[{p.persona}] claim: {p.claim}\nrationale: {p.rationale}" for p in positions
    )
    return (
        f"Design question: {task.question}\n\nContext: {task.context}\n\n"
        f"The team's final positions:\n{block}\n\n"
        f"Synthesize the team's joint decision. {SYNTHESIZE_MARKER} with keys "
        '"recommendation" (string), "alternatives" (list of strings), '
        '"risks" (list of strings), "rationale" (string).'
    )


def register_personas(
    mesh: AgentMesh, model: ChatModel, personas: list[Persona] | None = None
) -> None:
    """Register each persona as a mesh agent handling TurnRequest turns."""
    board = Blackboard(mesh)

    for persona in personas or PERSONAS:
        if persona.name in mesh._agents:
            continue  # already registered on this mesh (e.g. repeated runs)

        def _make(p: Persona):
            async def take_turn(req: TurnRequest) -> TurnResult:
                task = await board.read_task(req.task_id)
                positions = await board.read_positions(req.task_id)

                if req.phase == "synthesize":
                    reply = await model.complete(
                        p.system, _synthesize_prompt(task, list(positions.values()))
                    )
                    report_usage(Usage(
                        input_tokens=reply.input_tokens,
                        output_tokens=reply.output_tokens,
                        model=reply.model,
                    ))
                    decision = parse_decision(
                        reply.text, req.task_id, p.name, req.converged_early
                    )
                    await board.write_decision(req.task_id, decision)
                    return TurnResult(persona=p.name, round=req.round)

                own = positions.get(p.name)
                if req.phase == "position":
                    prompt = _position_prompt(task)
                else:
                    peers = [pos for name, pos in positions.items() if name != p.name]
                    prompt = _revise_prompt(task, own, peers)

                reply = await model.complete(p.system, prompt)
                report_usage(Usage(
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                    model=reply.model,
                ))

                claim, rationale = split_reply(reply.text)
                changed = own is None or own.claim != claim
                await board.write_position(req.task_id, Position(
                    persona=p.name,
                    claim=claim,
                    rationale=rationale,
                    revision=(own.revision if own else 0) + 1,
                ))
                await board.record_turn(req.task_id)
                return TurnResult(persona=p.name, round=req.round, changed=changed)

            return take_turn

        mesh.agent(AgentSpec(
            name=persona.name,
            description=(
                f"{persona.display} persona for team deliberations. Takes one "
                "debate turn per request; state lives on the blackboard."
            ),
        ))(_make(persona))


async def run_standing_team(
    mesh: AgentMesh,
    model: ChatModel,
    task: TaskBrief,
    *,
    personas: list[Persona] | None = None,
    rounds: int = 3,
    seed: int | None = None,
) -> Decision:
    """Run one full standing-team deliberation; returns the joint decision."""
    team = personas or PERSONAS
    register_personas(mesh, model, team)
    board = Blackboard(mesh)

    rng = random.Random(seed)
    order = [p.name for p in team]
    rng.shuffle(order)
    await board.open_debate(task, order, rounds)

    for name in order:
        await mesh.call(name, TurnRequest(task_id=task.task_id, phase="position"))

    converged = False
    for round_no in range(1, rounds + 1):
        await board.advance_round(task.task_id, round_no)
        any_changed = False
        for name in order:
            result = await mesh.call(name, TurnRequest(
                task_id=task.task_id, round=round_no, phase="revise"
            ))
            any_changed = any_changed or result["changed"]
        if not any_changed:
            converged = True
            break

    scribe = rng.choice(order)
    await mesh.call(scribe, TurnRequest(
        task_id=task.task_id, phase="synthesize", converged_early=converged
    ))

    decision = await board.read_decision(task.task_id)
    assert decision is not None, "synthesize turn did not write a decision"
    return decision
