"""CLI for the persona-team experiment.

Dry run of the machinery (offline, deterministic, synthetic numbers)::

    python -m openagentmesh.demos.persona_team --stub

Measured runs (require OPENROUTER_API_KEY; slugs are OpenRouter model ids)::

    python -m openagentmesh.demos.persona_team \
        --model anthropic/claude-sonnet-4.5 --runs 3 --out results.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import cast

from openagentmesh import AgentMesh

from .llm import OpenRouterModel, StubModel
from .personas import EAGER_REGISTRATION_TASK
from .records import TaskBrief
from .runner import RunReport, Topology, run_experiment


def _summarize(report: RunReport) -> str:
    cost = (
        f"${report.estimated_cost_usd:.4f}"
        if report.estimated_cost_usd is not None
        else "n/a"
    )
    tag = " [SYNTHETIC — stub model, not a result]" if report.synthetic else ""
    return (
        f"{report.topology:>12}: {report.wall_time_s:6.2f}s  "
        f"in={report.total_input_tokens} out={report.total_output_tokens} "
        f"cost={cost} msgs={report.message_count} "
        f"agents={len(report.usage_by_agent)}{tag}"
    )


async def _run(args: argparse.Namespace) -> list[RunReport]:
    reports: list[RunReport] = []
    topologies: list[Topology] = (
        ["standing", "hierarchical"]
        if args.topology == "both"
        else [cast("Topology", args.topology)]
    )

    for topology in topologies:
        for i in range(args.runs):
            task = TaskBrief(
                task_id=f"{EAGER_REGISTRATION_TASK.task_id}-{topology}-{i}",
                question=EAGER_REGISTRATION_TASK.question,
                context=EAGER_REGISTRATION_TASK.context,
            )
            model = StubModel() if args.stub else OpenRouterModel(args.model)
            # A fresh embedded mesh per run: no cross-run KV or agent state.
            async with AgentMesh.local() as mesh:
                report = await run_experiment(
                    mesh, model, topology, task,
                    rounds=args.rounds,
                    seed=args.seed + i if args.seed is not None else None,
                )
            reports.append(report)
            print(_summarize(report))

    if args.out:
        with Path(args.out).open("a", encoding="utf-8") as f:
            for report in reports:
                f.write(report.model_dump_json() + "\n")
        print(f"appended {len(reports)} report(s) to {args.out}")
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m openagentmesh.demos.persona_team",
        description="Standing team vs. hierarchical spawn, measured on a local mesh.",
    )
    parser.add_argument("--topology", choices=["standing", "hierarchical", "both"],
                        default="both")
    parser.add_argument("--runs", type=int, default=1, help="runs per topology")
    parser.add_argument("--rounds", type=int, default=3, help="max Delphi revision rounds")
    parser.add_argument("--model", default="anthropic/claude-sonnet-4.5",
                        help="OpenRouter model slug")
    parser.add_argument("--stub", action="store_true",
                        help="offline dry run with the deterministic stub model")
    parser.add_argument("--seed", type=int, default=None, help="turn-order seed")
    parser.add_argument("--out", default=None, help="append RunReport JSONL here")
    args = parser.parse_args()

    if args.stub:
        print("stub mode: machinery dry run — all numbers are SYNTHETIC", file=sys.stderr)

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
