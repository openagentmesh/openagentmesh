"""Stage 4 persona-team experiment: standing team vs. hierarchical spawn.

Research machinery, not SDK surface — a consumer of shipped primitives
(KV blackboard, call, observe/usage). Design and measurement plan:
km/notes/2026-07-20-persona-experiment-plan.md.

Dry runs (deterministic, offline)::

    python -m openagentmesh.demos.persona_team --stub

Measured runs need OPENROUTER_API_KEY (numbers from stub runs are synthetic
and never reportable).
"""

from .blackboard import Blackboard
from .hierarchical import register_hierarchy, run_hierarchical
from .llm import ChatModel, ModelReply, OpenRouterModel, StubModel
from .personas import EAGER_REGISTRATION_TASK, PERSONAS, Persona
from .records import (
    Decision,
    Position,
    RoundState,
    TaskBrief,
    TurnRequest,
    TurnResult,
)
from .runner import AgentUsage, RunReport, run_experiment
from .standing_team import register_personas, run_standing_team

__all__ = [
    "AgentUsage",
    "Blackboard",
    "ChatModel",
    "Decision",
    "EAGER_REGISTRATION_TASK",
    "ModelReply",
    "OpenRouterModel",
    "PERSONAS",
    "Persona",
    "Position",
    "RoundState",
    "RunReport",
    "StubModel",
    "TaskBrief",
    "TurnRequest",
    "TurnResult",
    "register_hierarchy",
    "register_personas",
    "run_experiment",
    "run_hierarchical",
    "run_standing_team",
]
