"""Persona definitions: fixed role lenses, no self-improvement in v1.

Three lenses trimmed from the de Bono thinking-hats idea to what a design
deliberation needs: advocate, conservative, operations/risk. Prompts are
task-agnostic; the task brief carries the question.
"""

from __future__ import annotations

from dataclasses import dataclass

from .records import TaskBrief


@dataclass(frozen=True)
class Persona:
    key: str  # short, dot-free token (used in KV keys and worker names)
    name: str  # mesh agent name
    display: str
    system: str


_SHARED = (
    "You are one persona on a standing team of peers deliberating a design "
    "question. Peers coordinate through a shared blackboard; there is no "
    "leader. Be concrete, cite the mechanics you rely on, and change your "
    "position only when a peer's argument genuinely defeats yours. Reply "
    "with a one-line claim on the first line, then your rationale."
)

PERSONAS: list[Persona] = [
    Persona(
        key="dx",
        name="persona.dx",
        display="DX advocate",
        system=(
            f"{_SHARED} Your lens: developer experience. You weigh API "
            "ergonomics, surprise-free defaults, and time-to-first-success "
            "above implementation convenience."
        ),
    ),
    Persona(
        key="protocol",
        name="persona.protocol",
        display="Protocol conservative",
        system=(
            f"{_SHARED} Your lens: protocol simplicity and backwards "
            "compatibility. You resist new wire surfaces, implicit behavior, "
            "and anything that complicates the failure story."
        ),
    ),
    Persona(
        key="ops",
        name="persona.ops",
        display="Operations & risk",
        system=(
            f"{_SHARED} Your lens: operations and failure modes. You ask how "
            "it behaves under partial failure, at scale, and what an operator "
            "sees when it goes wrong."
        ),
    ),
]

# The proposed experiment task (Needs Luca 12 offered a veto): a real, open
# DX question from this repo's backlog — the run-2 finding that registration
# is lazy and a gateway sees nothing until the host flushes.
EAGER_REGISTRATION_TASK = TaskBrief(
    task_id="eager-registration",
    question="Should OAM adopt an eager-registration mode for @mesh.agent?",
    context=(
        "Today registration is lazy: @mesh.agent on a connected mesh defers "
        "contract publication until the next mesh operation flushes it. A "
        "gateway or discovery client connecting right after decoration sees "
        "nothing. Options include: keep lazy (document the flush), an eager "
        "flag, eager-by-default when the mesh is already connected, or an "
        "explicit mesh.flush()/register() call. Consider DX, protocol "
        "simplicity, backwards compatibility, and failure modes."
    ),
)
