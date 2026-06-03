# eval/gate_check.py
from __future__ import annotations
import argparse
import json
import pathlib
import sys
import yaml
from eval.schemas import ABResult, EvalResult, GateDecision

TASK_WEIGHTS = {
    "booking_flow": 3.0,
    "flight_search": 2.0,
    "hotel_search": 2.0,
    "itinerary_build": 1.5,
    "fare_rules": 1.0,
    "edge_cases": 0.5,
}


def load_thresholds(path: str = "eval/gate_thresholds.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def compute_weighted_delta(results, weights: dict) -> float:
    total_weight = sum(weights.get(r.domain, 1.0) for r in results)
    if total_weight == 0:
        return 0.0
    return sum(r.delta * weights.get(r.domain, 1.0) for r in results) / total_weight


def gate_check(
    results,
    thresholds_path: str = "eval/gate_thresholds.yaml",
    langsmith_url: str = "",
) -> GateDecision:
    t = load_thresholds(thresholds_path)
    t1, t2, t3 = t["tier1"], t["tier2"], t["tier3"]

    weighted_delta = compute_weighted_delta(results, TASK_WEIGHTS)
    regression_rate = sum(1 for r in results if r.delta < 0) / len(results) if results else 0.0

    critical = [
        r for r in results
        if TASK_WEIGHTS.get(r.domain, 1.0) >= 3.0 and r.delta < t1["critical_task_delta_min"]
    ]
    heavy_regressions = [
        r for r in results
        if TASK_WEIGHTS.get(r.domain, 1.0) >= 2.0 and r.delta < t2["heavy_task_delta_min"]
    ]

    # Tier 1 — hard block
    if critical or weighted_delta < t1["weighted_delta_min"] or regression_rate > t1["regression_rate_max"]:
        return GateDecision(
            verdict="BLOCK", tier=1,
            weighted_delta=weighted_delta,
            regression_rate=regression_rate,
            flagged_tasks=[r.task_id for r in critical],
            langsmith_experiment_url=langsmith_url,
            override_allowed=False,
        )

    # Tier 2 — soft block
    if heavy_regressions or weighted_delta < t2["weighted_delta_min"] or regression_rate > t2["regression_rate_max"]:
        return GateDecision(
            verdict="SOFT_BLOCK", tier=2,
            weighted_delta=weighted_delta,
            regression_rate=regression_rate,
            flagged_tasks=[r.task_id for r in heavy_regressions],
            langsmith_experiment_url=langsmith_url,
            override_allowed=True,
        )

    # Tier 3 — warn
    small_regressions = [r for r in results if t3["small_regression_delta_min"] < r.delta < 0]
    if small_regressions:
        return GateDecision(
            verdict="WARN", tier=3,
            weighted_delta=weighted_delta,
            regression_rate=regression_rate,
            flagged_tasks=[r.task_id for r in small_regressions],
            langsmith_experiment_url=langsmith_url,
            override_allowed=True,
        )

    return GateDecision(
        verdict="PASS", tier=0,
        weighted_delta=weighted_delta,
        regression_rate=regression_rate,
        flagged_tasks=[],
        langsmith_experiment_url=langsmith_url,
        override_allowed=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="ab_results.json")
    args = parser.parse_args()

    raw = json.loads(pathlib.Path(args.results).read_text())
    results = []
    for r in raw:
        no_eval = EvalResult(**r["no_skill"])
        with_eval = EvalResult(**r["with_skill"])
        ab = ABResult.from_pair(r["skill_name"], no_eval, with_eval, r["task_weight"])
        results.append(ab)

    decision = gate_check(results)

    icon = {"PASS": "✓", "WARN": "⚠", "SOFT_BLOCK": "✗", "BLOCK": "✗✗"}[decision.verdict]
    print(f"\nGate Decision: {icon} {decision.verdict} (Tier {decision.tier})")
    print(f"  Weighted delta:  {decision.weighted_delta:+.3f}")
    print(f"  Regression rate: {decision.regression_rate:.0%}")
    if decision.flagged_tasks:
        print(f"  Flagged tasks:   {', '.join(decision.flagged_tasks)}")

    if decision.tier in (1, 2):
        sys.exit(1)
