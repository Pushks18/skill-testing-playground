# eval/ab_compare.py
"""Async A/B harness: runs no_skill vs with_skill for all tasks matching a skill name."""
from __future__ import annotations
from dotenv import load_dotenv; load_dotenv()
import argparse
import asyncio
import dataclasses
import json
import os
import pathlib
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from eval.run_task import run_task
from eval.schemas import ABResult
from eval.gate_check import gate_check, TASK_WEIGHTS
from eval.cost import cost_summary, format_cost

N_TRIALS = int(os.environ.get("EVAL_TRIALS", "5"))


def load_tasks_for_skill(skill_name: str, skill_path: pathlib.Path | None = None):
    """Find tasks for a skill — exact match first, semantic fallback second."""
    import re
    tasks_dir = pathlib.Path("tasks")
    exact = []
    unmatched = []

    for task_dir in sorted(tasks_dir.iterdir()):
        toml_path = task_dir / "task.toml"
        if not toml_path.exists():
            continue
        content = toml_path.read_text()
        m = re.search(r'^skill\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            if m.group(1) == skill_name:
                exact.append(task_dir)
        else:
            unmatched.append(task_dir)

    if exact:
        return exact

    # Semantic fallback — only runs when no exact match found AND skill path known
    if skill_path is None or not unmatched:
        return []

    try:
        from eval.skill_router import SkillRouter
        # Build router from just this one skill so we only need its description
        router = SkillRouter.from_skill_paths([skill_path])
        semantic = []
        for task_dir in unmatched:
            instr = (task_dir / "instruction.md")
            if not instr.exists():
                continue
            match = router.route(instr.read_text().strip(), threshold=0.35)
            if match and match.skill_name == skill_name:
                semantic.append(task_dir)
                print(f"  [semantic] matched {task_dir.name} → {skill_name} (score={match.score:.2f})")
        return semantic
    except Exception as e:
        print(f"  [semantic] router unavailable: {e}")
        return []


async def run_ab_for_task(task_path, skill_path, n_trials: int) -> ABResult:
    loop = asyncio.get_event_loop()

    no_skill_results = []
    with_skill_results = []
    for _ in range(n_trials):
        r_no = await loop.run_in_executor(None, run_task, str(task_path), None, "no_skill")
        r_with = await loop.run_in_executor(None, run_task, str(task_path), str(skill_path), "with_skill")
        no_skill_results.append(r_no)
        with_skill_results.append(r_with)

    best_no = max(no_skill_results, key=lambda r: r.score)
    best_with = max(with_skill_results, key=lambda r: r.score)

    import re
    content = (task_path / "task.toml").read_text()
    m = re.search(r'^domain\s*=\s*"([^"]+)"', content, re.MULTILINE)
    domain = m.group(1) if m else "unknown"
    weight = TASK_WEIGHTS.get(domain, 1.0)

    return ABResult.from_pair(
        skill_name=pathlib.Path(skill_path).name,
        no_skill=best_no,
        with_skill=best_with,
        task_weight=weight,
    )


async def run_ab_compare(skill_name: str, skill_path, n_trials: int):
    tasks = load_tasks_for_skill(skill_name, pathlib.Path(skill_path))
    if not tasks:
        print(f"No tasks found for skill '{skill_name}'")
        return []
    coros = [run_ab_for_task(t, skill_path, n_trials) for t in tasks]
    return await asyncio.gather(*coros)


def print_report(results, decision):
    if not results:
        return
    print(f"\nA/B Evaluation: {results[0].skill_name}  (N={N_TRIALS} trials)")
    print("-" * 90)
    print(f"{'task':<30} {'weight':>6}  {'no_skill':>8}  {'with_skill':>10}  {'delta':>7}  {'lat_Δms':>8}  {'cost_Δ':>9}  flag")
    for r in sorted(results, key=lambda x: x.task_id):
        flag = "REGRESSION" if r.regression else ("+" if r.delta > 0.05 else "-")
        cost_d = format_cost(abs(r.cost_delta_usd))
        cost_sign = "+" if r.cost_delta_usd >= 0 else "-"
        print(f"{r.task_id:<30} {r.task_weight:>6.1f}  {r.no_skill.score:>8.2f}  {r.with_skill.score:>10.2f}  {r.delta:>+7.2f}  {r.latency_delta_ms:>+8}  {cost_sign}{cost_d:>8}  {flag}")
    print("-" * 90)
    print(f"Weighted delta: {decision.weighted_delta:+.3f}    Regression rate: {decision.regression_rate:.0%}")
    labels = {"PASS": "PASS", "WARN": "WARN", "SOFT_BLOCK": "SOFT BLOCK", "BLOCK": "BLOCK"}
    print(f"GATE VERDICT:  {labels[decision.verdict]} (Tier {decision.tier})")

    # Cost + latency breakdown
    no_skill_results  = [r.no_skill  for r in results]
    with_skill_results = [r.with_skill for r in results]
    ns = cost_summary(no_skill_results)
    ws = cost_summary(with_skill_results)
    print(f"\n{'':30}  {'no_skill':>12}  {'with_skill':>12}")
    print(f"{'total cost (USD)':<30}  {format_cost(ns['total_cost_usd']):>12}  {format_cost(ws['total_cost_usd']):>12}")
    print(f"{'avg cost / run (USD)':<30}  {format_cost(ns['avg_cost_usd']):>12}  {format_cost(ws['avg_cost_usd']):>12}")
    print(f"{'avg latency (ms)':<30}  {ns['avg_latency_ms']:>12}  {ws['avg_latency_ms']:>12}")
    print(f"{'p95 latency (ms)':<30}  {ns['p95_latency_ms']:>12}  {ws['p95_latency_ms']:>12}")
    print(f"{'total input tokens':<30}  {ns['total_input_tokens']:>12}  {ws['total_input_tokens']:>12}")
    print(f"{'total output tokens':<30}  {ns['total_output_tokens']:>12}  {ws['total_output_tokens']:>12}")


def _build_summary(results, decision) -> dict:
    """Produce the ab_results.json payload consumed by CI and the Streamlit UI."""
    regression_traces = {
        r.task_id: r.with_skill.langsmith_run_id
        for r in results
        if r.regression and r.with_skill.langsmith_run_id
    }
    no_skill_results   = [r.no_skill  for r in results]
    with_skill_results = [r.with_skill for r in results]
    return {
        "skill_name": results[0].skill_name if results else "",
        "weighted_delta": decision.weighted_delta,
        "regression_rate": decision.regression_rate,
        "verdict": decision.verdict,
        "tier": decision.tier,
        "flagged_tasks": decision.flagged_tasks,
        "regression_traces": regression_traces,
        "cost": {
            "no_skill":  cost_summary(no_skill_results),
            "with_skill": cost_summary(with_skill_results),
        },
        "tasks": [dataclasses.asdict(r) for r in results],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--skill",
        help="Skill sub-path inside skills/ (e.g. concrete/flight-search)",
    )
    group.add_argument(
        "--skill-path",
        dest="skill_path",
        help="Absolute or relative path to a skill directory containing SKILL.md",
    )
    parser.add_argument("--trials", type=int, default=N_TRIALS)
    parser.add_argument(
        "--output",
        default=None,
        help="JSON output path. Defaults to ab_results.json at project root.",
    )
    args = parser.parse_args()

    if args.skill_path:
        skill_path = pathlib.Path(args.skill_path).resolve()
    else:
        skill_path = pathlib.Path("skills") / args.skill
    skill_name = skill_path.name

    results = asyncio.run(run_ab_compare(skill_name, skill_path, args.trials))
    decision = gate_check(results)
    print_report(results, decision)

    output = args.output or "ab_results.json"
    summary = _build_summary(results, decision)
    pathlib.Path(output).write_text(json.dumps(summary, indent=2))
    print(f"\nResults written to {output}")

    # Also write per-skill archive
    archive = f"results/{skill_name}_ab_results.json"
    pathlib.Path(archive).parent.mkdir(exist_ok=True)
    pathlib.Path(archive).write_text(json.dumps(summary, indent=2))

    if decision.tier in (1, 2):
        sys.exit(1)
