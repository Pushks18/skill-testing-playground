# eval/leaderboard.py
"""Aggregate all ab_results.json files into a skill leaderboard."""
from __future__ import annotations
import argparse
import json
import pathlib
from collections import defaultdict
from datetime import datetime


def collect_results(results_dir):
    """Collect per-task result dicts keyed by skill name.

    Handles both result file formats:
    - New format: a JSON object with ``skill_name``, ``model``, ``tasks`` list,
      and pre-computed summary fields (written by _build_summary).
    - Old format: a plain JSON array of per-task result dicts.

    Returns ``dict[skill_name, list[task_dict]]`` — same as before so existing
    callers (skill_server._last_eval) are unaffected.
    """
    by_skill = defaultdict(list)
    for path in sorted(pathlib.Path(results_dir).rglob("*ab_results*.json")):
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                # New format — extract task rows and tag each with the model
                model = data.get("model", "unknown")
                skill_name = data.get("skill_name", "")
                for r in data.get("tasks", []):
                    r = dict(r)
                    r.setdefault("model", model)
                    by_skill[skill_name].append(r)
            else:
                # Old format — plain list
                for r in data:
                    r = dict(r)
                    r.setdefault("model", "unknown")
                    by_skill[r["skill_name"]].append(r)
        except (json.JSONDecodeError, KeyError):
            continue
    return dict(by_skill)


def summarize_skill(skill_name: str, results, model: str = None) -> dict:
    """Summarize task results for a skill.

    Args:
        skill_name: The skill identifier.
        results: List of per-task result dicts.
        model: Optional model filter.  When supplied only tasks whose
            ``model`` field matches are included.  Defaults to ``None``
            (aggregate across all models — existing behaviour).

    Returns a summary dict.  Always includes ``"model"`` (``"all"`` when
    aggregating across models, the specific model string otherwise).
    """
    if model is not None:
        results = [r for r in results if r.get("model", "unknown") == model]
    if not results:
        return {}
    total_w = sum(r.get("task_weight", 1.0) for r in results)
    weighted_delta = (
        sum(r["delta"] * r.get("task_weight", 1.0) for r in results) / total_w
        if total_w
        else 0
    )
    regression_rate = sum(1 for r in results if r["delta"] < 0) / len(results)
    return {
        "skill": skill_name,
        "model": model if model is not None else "all",
        "weighted_delta": round(weighted_delta, 3),
        "regression_rate": round(regression_rate, 2),
        "n_tasks": len(results),
    }


def summarize_by_model(skill_name: str, results) -> list[dict]:
    """Return one summary row per (skill, model) pair found in *results*.

    Legacy tasks without a ``model`` key are grouped under ``"unknown"``.
    """
    models = sorted({r.get("model", "unknown") for r in results})
    rows = []
    for m in models:
        s = summarize_skill(skill_name, results, model=m)
        if s:
            rows.append(s)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="results")
    parser.add_argument(
        "--by-model",
        action="store_true",
        default=False,
        help="Show one row per (skill, model) pair instead of aggregating across models.",
    )
    args = parser.parse_args()

    by_skill = collect_results(args.results_dir)
    if not by_skill:
        print("No ab_results.json files found.")
        return

    if args.by_model:
        rows = []
        for skill_name, results in by_skill.items():
            rows.extend(summarize_by_model(skill_name, results))
        rows.sort(key=lambda x: (x.get("skill", ""), x.get("model", "")))

        print(f"\nSkill Leaderboard (per model) -- {datetime.now().strftime('%Y-%m-%d')}")
        print("-" * 85)
        print(f"{'Skill':<25} {'Model':<30} {'delta (weighted)':>16}  {'Regr rate':>9}  {'N tasks':>7}")
        for s in rows:
            flag = "<- needs optimizer" if s.get("weighted_delta", 0) < 0.05 else ""
            print(
                f"{s['skill']:<25} {s.get('model', 'unknown'):<30} "
                f"{s['weighted_delta']:>+16.3f}  {s['regression_rate']:>9.0%}  "
                f"{s['n_tasks']:>7}  {flag}"
            )
    else:
        summaries = [summarize_skill(k, v) for k, v in by_skill.items()]
        summaries.sort(key=lambda x: x.get("weighted_delta", 0), reverse=True)

        print(f"\nSkill Leaderboard -- {datetime.now().strftime('%Y-%m-%d')}")
        print("-" * 65)
        print(f"{'Skill':<25} {'delta (weighted)':>16}  {'Regr rate':>9}  {'N tasks':>7}")
        for s in summaries:
            flag = "<- needs optimizer" if s.get("weighted_delta", 0) < 0.05 else ""
            print(
                f"{s['skill']:<25} {s['weighted_delta']:>+16.3f}  "
                f"{s['regression_rate']:>9.0%}  {s['n_tasks']:>7}  {flag}"
            )


if __name__ == "__main__":
    main()
