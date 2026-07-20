"""Shared-context blackboard over the ``mesh-context`` KV bucket.

KV, not JetStream: deliberation state is a read-modify-write surface
(current position per participant + round bookkeeping), not an append-only
firehose. Each persona owns its own position key, so position writes never
contend; the shared ``round`` record uses CAS with retry (``kv.update``).
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from .records import Decision, Position, RoundState, TaskBrief

if TYPE_CHECKING:
    from openagentmesh import AgentMesh


def _key(task_id: str, *parts: str) -> str:
    return ".".join(("debate", task_id, *parts))


class Blackboard:
    """Typed helpers over the debate key layout (see records.py)."""

    def __init__(self, mesh: AgentMesh):
        self._mesh = mesh

    async def open_debate(self, task: TaskBrief, order: list[str], rounds: int) -> None:
        """Seed the board: task brief + round state; clear any stale debate state."""
        # ">" not "*": persona names contain dots ("persona.dx" is two tokens)
        for entry in await self._mesh.kv.list(_key(task.task_id, "position", ">")):
            await self._mesh.kv.delete(entry.key)
        with suppress(Exception):  # no stale decision to clear
            await self._mesh.kv.delete(_key(task.task_id, "decision"))
        await self._mesh.kv.put(_key(task.task_id, "task"), task.model_dump_json())
        state = RoundState(total_rounds=rounds, order=list(order))
        await self._mesh.kv.put(_key(task.task_id, "round"), state.model_dump_json())

    async def read_task(self, task_id: str) -> TaskBrief:
        return TaskBrief.model_validate_json(await self._mesh.kv.get(_key(task_id, "task")))

    async def write_position(self, task_id: str, position: Position) -> None:
        await self._mesh.kv.put(
            _key(task_id, "position", position.persona), position.model_dump_json()
        )

    async def read_positions(self, task_id: str) -> dict[str, Position]:
        entries = await self._mesh.kv.list(_key(task_id, "position", ">"))
        positions = [Position.model_validate_json(e.value.decode()) for e in entries]
        return {p.persona: p for p in positions}

    async def read_round(self, task_id: str) -> RoundState:
        return RoundState.model_validate_json(await self._mesh.kv.get(_key(task_id, "round")))

    async def record_turn(self, task_id: str) -> None:
        """Count a taken turn on the shared round record (CAS with retry)."""

        def bump(value: str) -> str:
            state = RoundState.model_validate_json(value)
            state.turns_taken += 1
            return state.model_dump_json()

        await self._mesh.kv.update(_key(task_id, "round"), bump)

    async def advance_round(self, task_id: str, round_no: int) -> None:
        def advance(value: str) -> str:
            state = RoundState.model_validate_json(value)
            state.round = round_no
            return state.model_dump_json()

        await self._mesh.kv.update(_key(task_id, "round"), advance)

    async def write_decision(self, task_id: str, decision: Decision) -> None:
        await self._mesh.kv.put(_key(task_id, "decision"), decision.model_dump_json())

    async def read_decision(self, task_id: str) -> Decision | None:
        from nats.js.errors import KeyDeletedError, KeyNotFoundError

        try:
            raw = await self._mesh.kv.get(_key(task_id, "decision"))
        except (KeyNotFoundError, KeyDeletedError):
            return None
        return Decision.model_validate_json(raw)
