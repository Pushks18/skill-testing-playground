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
    # Same inline-table fix as eval.run_task.load_task (some task files use ":" not "=")
    raw = re.sub(r"\{[^}]+\}", lambda m: m.group(0).replace(": ", " = ").replace(":", " = "), raw)
    meta = tomllib.loads(raw)
    expected = meta.get("expected", {})
    return {
        "tools": expected.get("tools", []),
        "required_params": expected.get("required_params", {}),
    }


def extract_features(ab_task: dict, expected: dict) -> TrajectoryFeatures:
    """Build TrajectoryFeatures from one ab_results.json task entry (with_skill side)."""
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
        if tool_name in tools_called:
            provided = tool_params.get(tool_name, {})
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
