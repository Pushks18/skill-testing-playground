# eval/coverage.py
"""Compute skill coverage precision/recall from A/B results."""
from __future__ import annotations
from eval.schemas import ABResult, SkillCoverageMetrics

TRIGGER_TARGETS = {"precision": 0.85, "recall": 0.80, "no_trigger_precision": 0.90}


def compute_coverage_metrics(
    skill_name: str,
    results,
    trigger_precision: float,
    trigger_recall: float,
    no_trigger_precision: float,
) -> SkillCoverageMetrics:
    triggered_and_helped = sum(1 for r in results if r.delta > 0)
    triggered = len(results)
    relevant = triggered

    coverage_precision = triggered_and_helped / triggered if triggered > 0 else 0.0
    coverage_recall = triggered_and_helped / relevant if relevant > 0 else 0.0

    strategy = _select_strategy(coverage_precision, coverage_recall, trigger_precision, trigger_recall)

    return SkillCoverageMetrics(
        skill_name=skill_name,
        trigger_precision=trigger_precision,
        trigger_recall=trigger_recall,
        no_trigger_precision=no_trigger_precision,
        coverage_precision=coverage_precision,
        coverage_recall=coverage_recall,
        optimizer_strategy=strategy,
    )


def _select_strategy(cov_p: float, cov_r: float, trig_p: float, trig_r: float) -> str:
    if trig_p < 0.75:
        return "variant_1_tighten_triggers"
    if trig_r < 0.75:
        return "variant_2_broaden_triggers"
    if cov_p > 0.85 and cov_r > 0.80:
        return "variant_3_edge_case_handling"
    return "variant_4_focused_modules"


def print_coverage_report(metrics: SkillCoverageMetrics):
    print("\nSkill Coverage P/R:")
    p_flag = "✓" if metrics.trigger_precision >= TRIGGER_TARGETS["precision"] else "<- below target"
    r_flag = "✓" if metrics.trigger_recall >= TRIGGER_TARGETS["recall"] else "<- below target"
    print(f"  Trigger precision:   {metrics.trigger_precision:.2f}  {p_flag}")
    print(f"  Trigger recall:      {metrics.trigger_recall:.2f}  {r_flag}")
    print(f"  Coverage precision:  {metrics.coverage_precision:.2f}")
    print(f"  Coverage recall:     {metrics.coverage_recall:.2f}")
    print(f"  Optimizer strategy:  {metrics.optimizer_strategy}")
