# eval/classify_failures.py
"""Failure-layer classifier: routes each eval failure to skill content vs agent harness.

Reads ab_results.json, extracts deterministic TrajectoryFeatures per failed task,
labels the failure layer via ordered rules, and clusters by (layer, domain).
Rules-first — no LLM call (an LLM fallback for low-confidence traces is a
Slice-3 hook, deliberately not built here).

Usage:
    python -m eval.classify_failures --results ab_results.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from eval.schemas import TrajectoryFeatures, FailureClassification, LayerCluster
from eval.trajectory import classify_failure

# Layer → key in harness config (skill layers resolve per-skill instead)
HARNESS_TARGETS = {
    "harness:base_prompt": "agent/harness_config.yaml::base_system_prompt",
    "harness:tool_description": "agent/harness_config.yaml::tool_descriptions",
    "harness:node_prompt": "agent/harness_config.yaml::node_prompts",
}


def load_expected(task_dir: pathlib.Path) -> dict:
    """Read [expected] from a task.toml. Returns {"tools": [...], "required_params": {...}}."""
    toml_path = task_dir / "task.toml"
    if not toml_path.exists():
        return {"tools": [], "required_params": {}}
    raw = toml_path.read_text()
    # Mirrors the inline-table fix in eval.run_task.load_task (some task files use ":" not "=")
    raw = re.sub(r"\{[^}]+\}", lambda m: m.group(0).replace(": ", " = ").replace(":", " = "), raw)
    meta = tomllib.loads(raw)
    expected = meta.get("expected", {})
    return {
        "tools": expected.get("tools", []),
        "required_params": expected.get("required_params", {}),
    }


def extract_features(ab_task: dict, expected: dict) -> TrajectoryFeatures:
    """Build TrajectoryFeatures from one ab_results.json task entry (with_skill side).

    n_wrong_tool_calls counts calls, not unique tools (3 calls to one wrong tool = 3).
    """
    ws = ab_task["with_skill"]
    tools_called = ws.get("tools_called", [])
    tool_params = ws.get("tool_params", {})
    expected_tools = expected.get("tools", [])
    required_params = expected.get("required_params", {})

    called_any = len(tools_called) > 0
    first_tool = tools_called[0] if tools_called else None
    expected_first = expected_tools[0] if expected_tools else None
    n_wrong = sum(1 for t in tools_called if t not in expected_tools)
    n_repeats = len(tools_called) - len(set(tools_called))

    # Param quality: across expected tools that were called, what fraction of
    # required params were provided?
    n_missing_calls = 0
    matched, total_required = 0, 0
    for tool_name, params in required_params.items():
        if tool_name not in tools_called:
            # Required tool never called → all its required params are unmet
            n_missing_calls += 1
            total_required += len(params)
            continue
        provided = tool_params.get(tool_name, {})
        # Key-presence check only: a param explicitly set to None still counts
        # as provided (deliberate — value quality is the verifier's job)
        missing = [p for p in params if p not in provided]
        if missing:
            n_missing_calls += 1
        matched += len(params) - len(missing)
        total_required += len(params)
    param_match_rate = (matched / total_required) if total_required else (1.0 if called_any else 0.0)

    no_expected_tool_called = bool(expected_tools) and not any(
        t in tools_called for t in expected_tools
    )
    passed = ws.get("passed_verifier", False)

    return TrajectoryFeatures(
        task_id=ab_task["task_id"],
        domain=ab_task["domain"],
        task_weight=ab_task.get("task_weight", 1.0),
        skill_injected=True,
        n_tools_called=len(tools_called),
        called_any_tool=called_any,
        first_tool_name=first_tool,
        expected_first_tool=expected_first,
        first_tool_correct=(first_tool is not None and first_tool == expected_first),
        n_wrong_tool_calls=n_wrong,
        n_repeated_tool_calls=n_repeats,
        n_calls_missing_required_params=n_missing_calls,
        param_match_rate=param_match_rate,
        n_steps=ws.get("steps", 0),
        step_delta_vs_no_skill=ab_task.get("step_delta", 0),
        ended_without_tool_on_tool_task=no_expected_tool_called,
        looped_without_completion=(n_repeats > 0 and not passed),
        output_is_verbal_only=not called_any,
        verifier_score=ws.get("score", 0.0),
        delta_vs_no_skill=ab_task.get("delta", 0.0),
    )


def classify_layer(
    f: TrajectoryFeatures,
    no_skill_passed: bool,
    skill_name: str,
) -> FailureClassification:
    """Ordered rules mapping features → failure layer.

    Precedence (per spec): when both an over-prescription signal and a harness
    signature apply, prefer the harness label if no tools were called — the
    harness is the actionable lever — and record the competing signal.
    """
    over_prescription_signal = (
        f.skill_injected and no_skill_passed and f.delta_vs_no_skill <= -0.5
    )
    evidence: dict = {
        "called_any_tool": f.called_any_tool,
        "first_tool_name": f.first_tool_name,
        "n_wrong_tool_calls": f.n_wrong_tool_calls,
        "step_delta_vs_no_skill": f.step_delta_vs_no_skill,
        "param_match_rate": f.param_match_rate,
        "delta_vs_no_skill": f.delta_vs_no_skill,
    }

    def result(layer: str, confidence: float) -> FailureClassification:
        target = HARNESS_TARGETS.get(layer, f"skills/{skill_name}/SKILL.md")
        return FailureClassification(
            task_id=f.task_id, layer=layer, confidence=confidence,
            target_artifact=target, evidence=dict(evidence),  # snapshot — callers must not see later mutations
        )

    # 1. No tools on a tool task → base prompt failure (002/006 signature)
    if f.ended_without_tool_on_tool_task and not f.called_any_tool:
        if over_prescription_signal:
            evidence["competing_layer"] = "skill:over_prescription"
            return result("harness:base_prompt", 0.94)
        return result("harness:base_prompt", 0.90)

    # 2. Verification derail: looped, or multiple off-target tools with extra
    #    steps and the required tool never reached (003 signature)
    # multi-tool spiral: off-target first tool, 2+ calls, extra steps, required tool never reached
    if f.looped_without_completion or (
        not f.first_tool_correct
        and f.n_tools_called >= 2
        and f.step_delta_vs_no_skill > 0
        and f.ended_without_tool_on_tool_task
    ):
        if over_prescription_signal:
            evidence["competing_layer"] = "skill:over_prescription"
        return result("harness:node_prompt", 0.82)

    # 3. Wrong tool selected → tool description failure
    if not f.first_tool_correct and f.called_any_tool:
        return result("harness:tool_description", 0.85)

    # 4. Right tool, bad params → skill content failure
    if f.n_calls_missing_required_params > 0 or f.param_match_rate < 1.0:
        return result("skill:content", 0.80)

    # 5. Everything looked right but only with_skill fails badly → the skill
    #    text itself derailed quality (over-prescription)
    if over_prescription_signal:
        return result("skill:over_prescription", 0.85)

    # 6. Fallback: unexplained failure, lowest confidence — skill content
    return result("skill:content", 0.50)
