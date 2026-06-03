# eval/optimizer/optimizer.py
"""Pseudo-GRPO skill optimizer: generate K variants, score, select, iterate."""
from __future__ import annotations
import argparse
import json
import os
import pathlib

import openai

from eval.optimizer.variant_strategies import STRATEGIES, get_strategy_prompt
from eval.run_task import run_task

K = 5
MAX_ROUNDS = 5
THRESHOLD = 0.03
FAST_EVAL_TASKS = 8


def generate_variant(skill_content: str, failing_traces, strategy_key: str, client) -> str:
    prompt = get_strategy_prompt(strategy_key, skill_content, failing_traces)
    msg = client.chat.completions.create(
        model="google/gemini-2.5-flash",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.choices[0].message.content


def score_skill_content(skill_content: str, task_paths, skill_name: str, tmp_path) -> float:
    tmp_skill = pathlib.Path(tmp_path) / "SKILL.md"
    tmp_skill.write_text(skill_content)
    scores = []
    for task_path in list(task_paths)[:FAST_EVAL_TASKS]:
        try:
            r = run_task(str(task_path), str(tmp_path), "with_skill")
            scores.append(r.score)
        except Exception:
            scores.append(0.0)
    return sum(scores) / len(scores) if scores else 0.0


def get_failing_tasks(skill_name: str, ab_results_path: str):
    if not pathlib.Path(ab_results_path).exists():
        return list(pathlib.Path("tasks").iterdir())[:FAST_EVAL_TASKS]
    raw = json.loads(pathlib.Path(ab_results_path).read_text())
    failing_ids = {r["task_id"] for r in raw if r.get("delta", 0) < 0}
    all_tasks = list(pathlib.Path("tasks").iterdir())
    failing = [t for t in all_tasks if t.name in failing_ids]
    return failing[:FAST_EVAL_TASKS] if failing else all_tasks[:FAST_EVAL_TASKS]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True, help="e.g. concrete/fare-rules")
    parser.add_argument("--ab-results", default="ab_results.json")
    parser.add_argument("--output-dir", default="eval/optimizer_output")
    args = parser.parse_args()

    skill_path = pathlib.Path("skills") / args.skill
    skill_name = skill_path.name
    skill_content = (skill_path / "SKILL.md").read_text()

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = output_dir / "_tmp_variant"
    tmp_dir.mkdir(exist_ok=True)

    client = openai.OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )
    tasks = get_failing_tasks(skill_name, args.ab_results)
    failing_traces = [
        f"Task {t.name}: {(t / 'instruction.md').read_text().strip()[:100]}"
        for t in tasks if (t / "instruction.md").exists()
    ]

    strategy_keys = list(STRATEGIES.keys())
    baseline_score = score_skill_content(skill_content, tasks, skill_name, tmp_dir)
    print(f"\nOptimizer: {skill_name}")
    print(f"Baseline fast-eval score: {baseline_score:.2f}")

    current_best_content = skill_content
    current_best_score = baseline_score

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\nRound {round_num}: generating {K} variants...")
        variants = []
        for strategy_key in strategy_keys[:K]:
            variant = generate_variant(current_best_content, failing_traces, strategy_key, client)
            score = score_skill_content(variant, tasks, skill_name, tmp_dir)
            delta = score - baseline_score
            print(f"  {strategy_key:<35} {score:.2f}  {delta:+.2f}")
            variants.append((score, variant, strategy_key))

        variants.sort(key=lambda x: x[0], reverse=True)
        top_score, top_content, top_strategy = variants[0]

        if top_score > current_best_score + THRESHOLD:
            current_best_score = top_score
            current_best_content = top_content
        else:
            print(f"Converged after {round_num} rounds.")
            break

    output_file = output_dir / f"{skill_name}_proposed.md"
    output_file.write_text(current_best_content)

    print(f"\nProposed: {output_file} (score: {current_best_score:.2f} vs baseline {baseline_score:.2f})")
    print(f"Run full eval: python eval/ab_compare.py --skill {args.skill}")
    print("NOTE: Human review required before committing any proposed skill.")


if __name__ == "__main__":
    main()
