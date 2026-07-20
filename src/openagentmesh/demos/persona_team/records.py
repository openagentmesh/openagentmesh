"""Structured blackboard records for the persona-team experiment.

Coordination state is structured (Pydantic), not freeform prose, so peers
read and update shared work items deterministically. Key layout on the
``mesh-context`` bucket:

- ``debate.{task_id}.task`` -> :class:`TaskBrief`
- ``debate.{task_id}.round`` -> :class:`RoundState`
- ``debate.{task_id}.position.{persona}`` -> :class:`Position`
- ``debate.{task_id}.decision`` -> :class:`Decision`

Design note: km/notes/2026-07-20-persona-experiment-plan.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TaskBrief(BaseModel):
    """The question the team deliberates. Written once at debate open."""

    task_id: str
    question: str
    context: str = ""


class Position(BaseModel):
    """One persona's current stance. Each persona owns exactly one key."""

    persona: str
    claim: str
    rationale: str = ""
    revision: int = 0


class RoundState(BaseModel):
    """Delphi round bookkeeping. Round 0 is the independent-position phase."""

    round: int = 0
    total_rounds: int
    order: list[str]
    turns_taken: int = 0


class Decision(BaseModel):
    """The converged outcome, written by the synthesizing agent."""

    task_id: str
    recommendation: str
    alternatives: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    rationale: str = ""
    synthesized_by: str
    converged_early: bool = False


class TurnRequest(BaseModel):
    """A turn granted to a persona by the round-robin dispatcher."""

    task_id: str
    round: int = 0
    phase: Literal["position", "revise", "synthesize"] = "position"
    converged_early: bool = False


class TurnResult(BaseModel):
    persona: str
    round: int = 0
    changed: bool = True
