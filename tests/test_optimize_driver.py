# tests/test_optimize_driver.py
import json
import pathlib

import pytest
import yaml

from eval.optimizer.optimize import (
    resolve_target, qualifying_clusters, estimate_rollout_calls, write_proposed,
)


HARNESS_OPTIMIZABLE = ["base_system_prompt", "tool_descriptions.*", "node_prompts.*"]


def _cluster(layer, target, n=2, domain="ancillery"):
    return {"layer": layer, "domain": domain, "task_ids": [f"t{i}" for i in range(n)],
            "dominant_failure_mode": "NO_TOOL_CALL", "target_artifact": target,
            "n_failures": n}


def test_resolve_harness_target():
    c = _cluster("harness:base_prompt", "agent/harness_config.yaml::base_system_prompt")
    kind, key = resolve_target(c)
    assert kind == "harness" and key == "base_system_prompt"


def test_resolve_skill_target():
    c = _cluster("skill:content", "skills/ancillery-skill/SKILL.md")
    kind, key = resolve_target(c)
    assert kind == "skill" and key == "ancillery-skill"


def test_resolve_rejects_non_whitelisted_harness_key():
    c = _cluster("harness:base_prompt", "agent/harness_config.yaml::version")
    with pytest.raises(ValueError, match="not optimizable"):
        resolve_target(c, optimizable=HARNESS_OPTIMIZABLE)


def test_qualifying_clusters_thresholds():
    clusters = [
        _cluster("harness:base_prompt", "agent/harness_config.yaml::base_system_prompt", n=1),
        _cluster("skill:content", "skills/x/SKILL.md", n=1),     # too thin
        _cluster("skill:content", "skills/y/SKILL.md", n=2),
    ]
    qualified = qualifying_clusters(clusters)
    assert len(qualified) == 2          # harness n=1 ok, skill needs n>=2


def test_estimate_rollout_calls():
    # findings §8.2-8.3: baseline(sel) + per-step (train + sel) + eval_test
    # runs the test split TWICE (baseline + best). epochs=5, 1 step/epoch.
    est = estimate_rollout_calls(n_train=5, n_selection=3, n_test=2, epochs=5)
    assert est == 3 + 5 * (5 + 3) + 2 * 2


def test_write_proposed_harness(tmp_path):
    base = {"version": "1.0", "base_system_prompt": "old",
            "tool_descriptions": {"a": "x"}, "node_prompts": {},
            "optimizable": HARNESS_OPTIMIZABLE}
    base_path = tmp_path / "harness_config.yaml"
    base_path.write_text(yaml.safe_dump(base))
    out = write_proposed(kind="harness", key="base_system_prompt",
                         artifact_text="NEW PROMPT", out_dir=tmp_path,
                         harness_config_path=base_path, skill_path=None)
    assert out.name == "harness_config_proposed.yaml"
    proposed = yaml.safe_load(out.read_text())
    assert proposed["base_system_prompt"] == "NEW PROMPT"
    assert proposed["tool_descriptions"] == {"a": "x"}
    # the REAL config is untouched
    assert yaml.safe_load(base_path.read_text())["base_system_prompt"] == "old"


def test_write_proposed_skill(tmp_path):
    skill_dir = tmp_path / "ancillery-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: ancillery-skill\n---\n\n# Old Body\n")
    out = write_proposed(kind="skill", key="ancillery-skill",
                         artifact_text="# New Body", out_dir=tmp_path,
                         harness_config_path=None, skill_path=skill_dir)
    assert out.name == "SKILL_proposed.md"
    content = out.read_text()
    assert content.startswith("---")
    assert "# New Body" in content
    assert (skill_dir / "SKILL.md").read_text().count("# Old Body") == 1  # source untouched
