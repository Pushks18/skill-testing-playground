# eval/leaderboard.py
"""Aggregate all ab_results.json files into a skill leaderboard."""
from __future__ import annotations
import argparse
import json
import pathlib
from collections import defaultdict
from datetime import datetime


def collect_results(results_dir):
    by_skill = defaultdict(list)
    for path in sorted(pathlib.Path(results_dir).rglob("ab_results*.json")):
        try:
            data = json.loads(path.read_text())
            for r in data:
                by_skill[r["skill_name"]].append(r)
        except (json.JSONDecodeError, KeyError):
            continue
    return dict(by_skill)


def summarize_skill(skill_name: str, results) -> dict:
    if not results:
        return {}
    total_w = sum(r.get("task_weight", 1.0) for r in results)
    weighted_delta = sum(r["delta"] * r.get("task_weight", 1.0) for r in results) / total_w if total_w else 0
    regression_rate = sum(1 for r in results if r["delta"] < 0) / len(results)
    return {
        "skill": skill_name,
        "weighted_delta": round(weighted_delta, 3),
        "regression_rate": round(regression_rate, 2),
        "n_tasks": len(results),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default=".")
    args = parser.parse_args()

    by_skill = collect_results(args.results_dir)
    if not by_skill:
        print("No ab_results.json files found.")
        return

    summaries = [summarize_skill(k, v) for k, v in by_skill.items()]
    summaries.sort(key=lambda x: x.get("weighted_delta", 0), reverse=True)

    print(f"\nSkill Leaderboard -- {datetime.now().strftime('%Y-%m-%d')}")
    print("-" * 65)
    print(f"{'Skill':<25} {'delta (weighted)':>16}  {'Regr rate':>9}  {'N tasks':>7}")
    for s in summaries:
        flag = "<- needs optimizer" if s.get("weighted_delta", 0) < 0.05 else ""
        print(f"{s['skill']:<25} {s['weighted_delta']:>+16.3f}  {s['regression_rate']:>9.0%}  {s['n_tasks']:>7}  {flag}")


if __name__ == "__main__":
    main()
