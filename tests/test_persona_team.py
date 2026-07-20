"""Tests for the Stage 4 persona-team experiment machinery (demos/persona_team).

Both topologies — standing team (blackboard + randomized round-robin Delphi
rounds) and hierarchical spawn baseline — must run the full protocol dry with
a deterministic stub model. The stub's token numbers are synthetic: they
exercise the metering plumbing and are never experiment results.

Design note: km/notes/2026-07-20-persona-experiment-plan.md.
"""

import asyncio
import json

import pytest

from openagentmesh import AgentMesh
from openagentmesh.demos.persona_team import (
    PERSONAS,
    Blackboard,
    Decision,
    Position,
    RunReport,
    StubModel,
    TaskBrief,
    run_experiment,
    run_hierarchical,
    run_standing_team,
)

pytestmark = pytest.mark.asyncio


TASK = TaskBrief(
    task_id="debate-test",
    question="Should OAM adopt an eager-registration mode?",
    context="Registration is currently lazy: contracts publish on the next mesh operation.",
)


class TestBlackboard:
    async def test_positions_roundtrip(self):
        async with AgentMesh.local() as mesh:
            board = Blackboard(mesh)
            await board.open_debate(TASK, order=["persona.dx", "persona.ops"], rounds=2)

            assert (await board.read_task(TASK.task_id)).question == TASK.question

            await board.write_position(
                TASK.task_id,
                Position(persona="persona.dx", claim="yes", rationale="DX wins", revision=1),
            )
            positions = await board.read_positions(TASK.task_id)
            assert positions["persona.dx"].claim == "yes"
            assert positions["persona.dx"].revision == 1

    async def test_concurrent_position_writes_no_lost_updates(self):
        """Two personas writing concurrently must both land (CAS, no clobber)."""
        async with AgentMesh.local() as mesh:
            board = Blackboard(mesh)
            await board.open_debate(TASK, order=["persona.dx", "persona.ops"], rounds=1)

            await asyncio.gather(*[
                board.write_position(
                    TASK.task_id,
                    Position(persona=name, claim=f"claim-{name}", rationale="r", revision=1),
                )
                for name in ("persona.dx", "persona.ops")
            ])
            positions = await board.read_positions(TASK.task_id)
            assert set(positions) == {"persona.dx", "persona.ops"}

    async def test_decision_roundtrip(self):
        async with AgentMesh.local() as mesh:
            board = Blackboard(mesh)
            await board.open_debate(TASK, order=["persona.dx"], rounds=1)
            assert await board.read_decision(TASK.task_id) is None

            decision = Decision(
                task_id=TASK.task_id,
                recommendation="adopt eagerly",
                synthesized_by="persona.dx",
            )
            await board.write_decision(TASK.task_id, decision)
            stored = await board.read_decision(TASK.task_id)
            assert stored is not None
            assert stored.recommendation == "adopt eagerly"


class TestStandingTeam:
    async def test_dry_run_produces_decision(self):
        """3 personas, 2 Delphi revision rounds, stub model: full protocol runs."""
        async with AgentMesh.local() as mesh:
            decision = await run_standing_team(
                mesh, StubModel(), TASK, rounds=2, seed=7
            )
            assert isinstance(decision, Decision)
            assert decision.task_id == TASK.task_id
            assert decision.recommendation
            assert decision.synthesized_by in [p.name for p in PERSONAS]

            board = Blackboard(mesh)
            positions = await board.read_positions(TASK.task_id)
            assert set(positions) == {p.name for p in PERSONAS}
            # 1 initial position + 2 revision rounds
            assert all(p.revision == 3 for p in positions.values())

    async def test_converges_early_when_positions_stop_changing(self):
        """Stub frozen after the first revision: round 2/3 detects convergence."""
        async with AgentMesh.local() as mesh:
            decision = await run_standing_team(
                mesh, StubModel(converge_after=1), TASK, rounds=3, seed=7
            )
            assert decision.converged_early is True

            board = Blackboard(mesh)
            positions = await board.read_positions(TASK.task_id)
            # initial + round 1 revision + the round-2 unchanged revision that
            # triggered convergence detection; round 3 never ran
            assert all(p.revision <= 3 for p in positions.values())

    async def test_turn_order_is_seeded_and_fixed(self):
        """Same seed gives the same randomized round-robin order, recorded on the board."""
        async with AgentMesh.local() as mesh:
            await run_standing_team(mesh, StubModel(), TASK, rounds=1, seed=42)
            board = Blackboard(mesh)
            state = await board.read_round(TASK.task_id)
            assert sorted(state.order) == sorted(p.name for p in PERSONAS)

        async with AgentMesh.local() as mesh:
            await run_standing_team(mesh, StubModel(), TASK, rounds=1, seed=42)
            board = Blackboard(mesh)
            assert (await board.read_round(TASK.task_id)).order == state.order


class TestHierarchicalBaseline:
    async def test_dry_run_produces_decision(self):
        async with AgentMesh.local() as mesh:
            decision = await run_hierarchical(mesh, StubModel(), TASK)
            assert isinstance(decision, Decision)
            assert decision.task_id == TASK.task_id
            assert decision.recommendation
            assert decision.synthesized_by == "hier.orchestrator"


class TestExperimentRunner:
    async def test_standing_run_report_carries_measurements(self):
        async with AgentMesh.local() as mesh:
            report = await run_experiment(
                mesh, StubModel(), "standing", TASK, rounds=2, seed=7
            )
            assert isinstance(report, RunReport)
            assert report.topology == "standing"
            assert report.decision is not None
            assert report.wall_time_s > 0
            # stub reports synthetic token counts through report_usage();
            # the meter must see one usage_reported event per persona turn
            assert report.total_input_tokens > 0
            assert report.total_output_tokens > 0
            assert set(report.usage_by_agent) == {p.name for p in PERSONAS}
            assert report.message_count > 0

    async def test_hierarchical_run_report_attributes_all_agents(self):
        async with AgentMesh.local() as mesh:
            report = await run_experiment(mesh, StubModel(), "hierarchical", TASK)
            assert report.topology == "hierarchical"
            assert report.decision is not None
            # orchestrator + one worker per persona all report usage
            assert "hier.orchestrator" in report.usage_by_agent
            workers = {a for a in report.usage_by_agent if a.startswith("hier.worker.")}
            assert len(workers) == len(PERSONAS)

    async def test_report_json_roundtrip(self):
        async with AgentMesh.local() as mesh:
            report = await run_experiment(
                mesh, StubModel(), "standing", TASK, rounds=1, seed=1
            )
            restored = RunReport.model_validate(json.loads(report.model_dump_json()))
            assert restored.total_input_tokens == report.total_input_tokens
            assert restored.decision == report.decision
