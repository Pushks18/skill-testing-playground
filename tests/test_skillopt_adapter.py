# tests/test_skillopt_adapter.py
import pathlib

import pytest
import yaml

from eval.optimizer.skillopt_adapter import (
    TargetSpec, initial_artifact, materialize_candidate, TravelTaskLoader,
)

SKILL_MD = """---
name: ancillery-skill
description: Handle ancillary services.
metadata:
  version: "0.1.0"
---

# Ancillery Skill

## Workflow
1. Confirm required inputs.
"""

HARNESS_YAML = {
    "version": "1.0",
    "base_system_prompt": "You are a helpful travel assistant.",
    "tool_descriptions": {"add_ancillary": "Add an ancillary service."},
    "node_prompts": {},
    "optimizable": ["base_system_prompt", "tool_descriptions.*", "node_prompts.*"],
}


@pytest.fixture
def skill_dir(tmp_path):
    d = tmp_path / "ancillery-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(SKILL_MD)
    return d


@pytest.fixture
def harness_path(tmp_path):
    p = tmp_path / "harness_config.yaml"
    p.write_text(yaml.safe_dump(HARNESS_YAML))
    return p


def make_spec(kind, key, skill_dir, harness_path, tmp_path):
    return TargetSpec(kind=kind, key=key, skill_path=skill_dir,
                      domain="ancillery", tasks_dir=tmp_path / "tasks",
                      harness_config_path=harness_path)


def test_initial_artifact_skill_is_body_only(skill_dir, harness_path, tmp_path):
    spec = make_spec("skill", "ancillery-skill", skill_dir, harness_path, tmp_path)
    art = initial_artifact(spec)
    assert art.startswith("# Ancillery Skill")
    assert "---" not in art  # frontmatter stripped


def test_initial_artifact_harness_scalar_key(skill_dir, harness_path, tmp_path):
    spec = make_spec("harness", "base_system_prompt", skill_dir, harness_path, tmp_path)
    assert initial_artifact(spec) == "You are a helpful travel assistant."


def test_initial_artifact_harness_dict_key_is_yaml(skill_dir, harness_path, tmp_path):
    spec = make_spec("harness", "tool_descriptions", skill_dir, harness_path, tmp_path)
    art = initial_artifact(spec)
    assert yaml.safe_load(art) == {"add_ancillary": "Add an ancillary service."}


def test_materialize_skill_writes_candidate_dir(skill_dir, harness_path, tmp_path):
    spec = make_spec("skill", "ancillery-skill", skill_dir, harness_path, tmp_path)
    out = tmp_path / "out"
    ctx = materialize_candidate(spec, "# New Body\nStep 1.", out)
    candidate = ctx.skill_path / "SKILL.md"
    content = candidate.read_text()
    assert content.startswith("---")              # frontmatter reattached
    assert "name: ancillery-skill" in content
    assert "# New Body" in content
    assert ctx.harness_config_path is None        # skill target: no harness override


def test_materialize_harness_substitutes_key(skill_dir, harness_path, tmp_path):
    spec = make_spec("harness", "base_system_prompt", skill_dir, harness_path, tmp_path)
    out = tmp_path / "out"
    ctx = materialize_candidate(spec, "ALWAYS act. Call tools.", out)
    assert ctx.skill_path == skill_dir            # harness target: real skill injected
    written = yaml.safe_load(ctx.harness_config_path.read_text())
    assert written["base_system_prompt"] == "ALWAYS act. Call tools."
    # untouched keys preserved
    assert written["tool_descriptions"] == HARNESS_YAML["tool_descriptions"]
    assert written["optimizable"] == HARNESS_YAML["optimizable"]


def test_materialize_harness_dict_key_roundtrip(skill_dir, harness_path, tmp_path):
    spec = make_spec("harness", "tool_descriptions", skill_dir, harness_path, tmp_path)
    out = tmp_path / "out"
    new_yaml = yaml.safe_dump({"add_ancillary": "Call this IMMEDIATELY when asked."})
    ctx = materialize_candidate(spec, new_yaml, out)
    written = yaml.safe_load(ctx.harness_config_path.read_text())
    assert written["tool_descriptions"]["add_ancillary"].startswith("Call this IMMEDIATELY")


def test_materialize_harness_invalid_yaml_artifact_raises(skill_dir, harness_path, tmp_path):
    spec = make_spec("harness", "tool_descriptions", skill_dir, harness_path, tmp_path)
    with pytest.raises(ValueError, match="not valid YAML"):
        materialize_candidate(spec, "key: [unclosed", tmp_path / "out")


def test_materialize_skill_without_frontmatter_no_leading_blank(tmp_path, harness_path):
    bare = tmp_path / "bare-skill"
    bare.mkdir()
    (bare / "SKILL.md").write_text("# Bare Skill\nStep 1.\n")
    spec = TargetSpec(kind="skill", key="bare-skill", skill_path=bare,
                      domain="ancillery", tasks_dir=tmp_path / "tasks",
                      harness_config_path=harness_path)
    ctx = materialize_candidate(spec, "# New Body", tmp_path / "out")
    content = (ctx.skill_path / "SKILL.md").read_text()
    assert content == "# New Body\n"          # no leading blank line


def _write_task(tasks_dir, name, domain):
    d = tasks_dir / name
    d.mkdir(parents=True)
    (d / "task.toml").write_text(
        f'[task]\nid = "{name}"\ndomain = "{domain}"\nweight = 1.5\n\n'
        '[expected]\ntools = ["add_ancillary"]\n'
    )
    (d / "instruction.md").write_text(f"Instruction for {name}")
    return d


def test_loader_filters_by_domain(tmp_path):
    tasks = tmp_path / "tasks"
    for i in range(3):
        _write_task(tasks, f"ancillery-{i:03d}", "ancillery")
    _write_task(tasks, "hotel-001", "hotel_search")

    loader = TravelTaskLoader(tasks_dir=tasks, domain="ancillery",
                              split_ratio="5:3:2", split_seed=7, seed=7)
    items = loader.load_raw_items(str(tasks))
    assert len(items) == 3
    assert all(i["task_type"] == "ancillery" for i in items)
    assert all("task_path" in i and "question" in i and i["id"] for i in items)


def test_loader_skips_incomplete_task_dirs(tmp_path):
    tasks = tmp_path / "tasks"
    _write_task(tasks, "ancillery-001", "ancillery")
    (tasks / "broken-task").mkdir()          # no task.toml / instruction.md
    loader = TravelTaskLoader(tasks_dir=tasks, domain="ancillery")
    assert len(loader.load_raw_items(str(tasks))) == 1
