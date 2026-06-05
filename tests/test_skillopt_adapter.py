# tests/test_skillopt_adapter.py
import os
import pathlib

import pytest
import yaml

from eval.optimizer.skillopt_adapter import (
    TargetSpec, initial_artifact, materialize_candidate, TravelTaskLoader,
    TravelEnvAdapter,
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


# ── skillopt_prompts tests ─────────────────────────────────────────────────────

def test_install_prompts_covers_reachable_names():
    """All aggregate merge names resolve after install_prompts(), and every
    prompt text contains an output-format instruction."""
    from eval.optimizer.skillopt_prompts import PROMPTS, install_prompts
    install_prompts()
    import skillopt.gradient.aggregate as agg
    for name in ("merge_failure", "merge_success", "merge_final"):
        text = agg.load_prompt(name)
        assert text, f"merge prompt {name!r} resolved to empty string"
    for name, text in PROMPTS.items():
        assert "edits" in text or "JSON" in text or "slow_update_content" in text or "meta_skill_content" in text or "selected_indices" in text, (
            f"prompt {name!r} lacks output-format instruction"
        )


def test_install_prompts_reflect_names_resolve():
    """The exact names reflect.py requests in patch mode must be covered."""
    from eval.optimizer.skillopt_prompts import install_prompts
    install_prompts()
    import skillopt.gradient.reflect as refl
    # In patch mode, _resolve_prompt(None, "analyst_error", "patch")
    # → load_prompt("analyst_error")
    # In patch mode, _resolve_prompt(None, "analyst_success", "patch")
    # → load_prompt("analyst_success")
    assert refl.load_prompt("analyst_error"), "analyst_error prompt is empty"
    assert refl.load_prompt("analyst_success"), "analyst_success prompt is empty"


def test_install_prompts_clip_name_resolves():
    """clip.py ranking prompt name resolves after install_prompts()."""
    from eval.optimizer.skillopt_prompts import install_prompts
    install_prompts()
    import skillopt.optimizer.clip as clip
    assert clip.load_prompt("ranking"), "ranking prompt is empty"


def test_install_prompts_slow_update_resolves():
    """slow_update.py prompt resolves after install_prompts()."""
    from eval.optimizer.skillopt_prompts import install_prompts
    install_prompts()
    import skillopt.optimizer.slow_update as slow
    assert slow.load_prompt("slow_update"), "slow_update prompt is empty"


def test_install_prompts_meta_skill_resolves():
    """meta_skill.py prompt resolves after install_prompts()."""
    from eval.optimizer.skillopt_prompts import install_prompts
    install_prompts()
    import skillopt.optimizer.meta_skill as meta
    assert meta.load_prompt("meta_skill"), "meta_skill prompt is empty"


def test_install_prompts_fallback_to_original_for_unknown():
    """load_prompt still raises FileNotFoundError for truly unknown names."""
    from eval.optimizer.skillopt_prompts import install_prompts
    install_prompts()
    import skillopt.gradient.reflect as refl
    import pytest
    with pytest.raises(FileNotFoundError):
        refl.load_prompt("__this_name_does_not_exist_anywhere__")


def test_analyst_error_prompt_round_trip():
    """Verify extract_json can parse a synthetic model response following the
    analyst_error prompt's output-format specification.

    This is the closest we can get to a round-trip without a live LLM call:
    we hand-author a response that exactly follows our prompt's instructions
    and confirm skillopt's own parser accepts it.
    """
    from skillopt.utils import extract_json

    # Synthetic response in the WRAPPED form the prompt specifies
    # (with markdown fences — extract_json handles both fences and bare JSON)
    fake_response = """
```json
{
  "patch": {
    "reasoning": "Agent failed to call search_flights and responded verbally instead.",
    "edits": [
      {
        "op": "insert_after",
        "content": "ALWAYS call search_flights before providing any flight information.",
        "target": "## Workflow"
      },
      {
        "op": "append",
        "content": "Never respond verbally about flight availability; always call the tool."
      }
    ]
  },
  "source_type": "failure"
}
```
"""
    result = extract_json(fake_response)
    assert result is not None, "extract_json returned None for synthetic response"
    assert "patch" in result, "outer 'patch' key missing"
    patch = result["patch"]
    assert "edits" in patch, "inner 'edits' key missing"
    edits = patch["edits"]
    assert len(edits) == 2
    # Verify op/content/target fields on each edit
    assert edits[0]["op"] == "insert_after"
    assert edits[0]["target"] == "## Workflow"
    assert "content" in edits[0]
    assert edits[1]["op"] == "append"
    assert "content" in edits[1]
    # Verify source_type at outer level (as reflect.py sets it)
    assert result["source_type"] == "failure"


def test_merge_patch_round_trip():
    """Verify extract_json can parse a synthetic merge response (flat edits form)."""
    from skillopt.utils import extract_json

    fake_response = """{
  "reasoning": "Merged three failure patches; deduplicated two search_flights edits.",
  "edits": [
    {
      "op": "replace",
      "target": "Use verbal confirmation when no flights are found.",
      "content": "Always call search_flights; never give verbal-only flight answers."
    },
    {
      "op": "delete",
      "target": "You may respond directly if the user asks a simple question."
    }
  ]
}"""
    result = extract_json(fake_response)
    assert result is not None
    assert "edits" in result
    assert result["reasoning"].startswith("Merged")
    edits = result["edits"]
    assert len(edits) == 2
    assert edits[0]["op"] == "replace"
    assert "target" in edits[0]
    assert "content" in edits[0]
    assert edits[1]["op"] == "delete"
    assert "target" in edits[1]


def test_ranking_round_trip():
    """Verify extract_json can parse a synthetic ranking response."""
    from skillopt.utils import extract_json

    fake_response = """{
  "selected_indices": [2, 0, 4],
  "reasoning": "Edits 2 and 0 address the most common failure patterns."
}"""
    result = extract_json(fake_response)
    assert result is not None
    assert "selected_indices" in result
    assert result["selected_indices"] == [2, 0, 4]


def test_slow_update_round_trip():
    """Verify extract_json can parse a synthetic slow_update response."""
    from skillopt.utils import extract_json

    fake_response = """{
  "reasoning": "Epoch 2 added too many verbose explanations causing regressions on quick-lookup tasks.",
  "slow_update_content": "Avoid adding explanatory paragraphs. Keep all instructions action-directive style."
}"""
    result = extract_json(fake_response)
    assert result is not None
    assert result.get("slow_update_content"), "slow_update_content missing or empty"


def test_meta_skill_round_trip():
    """Verify extract_json can parse a synthetic meta_skill response."""
    from skillopt.utils import extract_json

    fake_response = """{
  "reasoning": "Edits that clarified required parameters consistently improved hard scores.",
  "meta_skill_content": "Prioritize edits that list required parameters explicitly. Avoid edits that add verbose preamble."
}"""
    result = extract_json(fake_response)
    assert result is not None
    assert result.get("meta_skill_content"), "meta_skill_content missing or empty"


def test_all_prompts_contain_edit_op_vocabulary():
    """Prompts that generate edits must mention the op vocabulary.
    The ranking prompt is excluded: it selects indices into an existing
    edit pool and does not need to specify the op vocabulary itself."""
    from eval.optimizer.skillopt_prompts import PROMPTS
    # Prompts that instruct the model to GENERATE edits must include op vocab
    edit_generating_prompts = ("analyst_error", "analyst_success",
                               "merge_failure", "merge_success", "merge_final")
    for name in edit_generating_prompts:
        assert name in PROMPTS, f"PROMPTS is missing required entry {name!r}"
        text = PROMPTS[name]
        assert "append" in text, f"prompt {name!r} does not mention 'append'"
        assert "insert_after" in text, f"prompt {name!r} does not mention 'insert_after'"
        assert "replace" in text, f"prompt {name!r} does not mention 'replace'"
        assert "delete" in text, f"prompt {name!r} does not mention 'delete'"
    # ranking prompt must specify its own output format instead
    assert "ranking" in PROMPTS
    assert "selected_indices" in PROMPTS["ranking"]


# ── TravelEnvAdapter rollout tests ─────────────────────────────────────────────

class _FakeEvalResult:
    def __init__(self, score, passed, reason=""):
        self.score = score
        self.passed_verifier = passed
        self.judge_reasoning = reason
        self.tools_called = []
        self.tool_params = {}


def _make_adapter(tmp_path, skill_dir, harness_path, kind="harness", key="base_system_prompt"):
    tasks = tmp_path / "tasks"
    for i in range(3):
        _write_task(tasks, f"ancillery-{i:03d}", "ancillery")
    spec = TargetSpec(kind=kind, key=key, skill_path=skill_dir, domain="ancillery",
                      tasks_dir=tasks, harness_config_path=harness_path)
    return TravelEnvAdapter(spec=spec, mock_mcp_url="http://localhost:8000")


def test_rollout_shapes_results(tmp_path, skill_dir, harness_path, monkeypatch):
    monkeypatch.delenv("HARNESS_CONFIG_PATH", raising=False)
    adapter = _make_adapter(tmp_path, skill_dir, harness_path)
    calls = []

    def fake_run_task(task_path, skill_path, condition, mock_mcp_url):
        calls.append({"task_path": task_path, "skill_path": skill_path,
                      "condition": condition,
                      "harness_env": os.environ.get("HARNESS_CONFIG_PATH")})
        return _FakeEvalResult(score=0.5, passed=False, reason="missing tool")

    import eval.optimizer.skillopt_adapter as mod
    monkeypatch.setattr(mod, "run_task", fake_run_task)

    items = [{"id": f"ancillery-{i:03d}", "question": f"q{i}", "task_type": "ancillery",
              "task_path": str(tmp_path / "tasks" / f"ancillery-{i:03d}")} for i in range(3)]
    results = adapter.rollout(items, "CANDIDATE PROMPT", str(tmp_path / "roll"))

    assert len(results) == 3
    for r in results:
        assert set(r) >= {"id", "hard", "soft", "fail_reason", "task_type"}
        assert r["hard"] == 0 and r["soft"] == 0.5
    # condition that exposed the failure: with_skill, real skill injected
    assert all(c["condition"] == "with_skill" for c in calls)
    assert all(c["skill_path"] == str(skill_dir) for c in calls)
    # candidate harness config was active DURING rollout...
    assert all(c["harness_env"] and "candidate_harness_config" in c["harness_env"] for c in calls)
    # ...and restored afterward
    assert os.environ.get("HARNESS_CONFIG_PATH") is None


def test_rollout_restores_env_var_on_crash(tmp_path, skill_dir, harness_path, monkeypatch):
    monkeypatch.delenv("HARNESS_CONFIG_PATH", raising=False)
    adapter = _make_adapter(tmp_path, skill_dir, harness_path)

    def exploding_run_task(*a, **kw):
        raise RuntimeError("boom")

    import eval.optimizer.skillopt_adapter as mod
    monkeypatch.setattr(mod, "run_task", exploding_run_task)
    items = [{"id": "ancillery-000", "question": "q", "task_type": "ancillery",
              "task_path": str(tmp_path / "tasks" / "ancillery-000")}]
    with pytest.raises(RuntimeError):
        adapter.rollout(items, "X", str(tmp_path / "roll"))
    assert os.environ.get("HARNESS_CONFIG_PATH") is None


def test_rollout_skill_target_uses_candidate_skill(tmp_path, skill_dir, harness_path, monkeypatch):
    monkeypatch.delenv("HARNESS_CONFIG_PATH", raising=False)
    adapter = _make_adapter(tmp_path, skill_dir, harness_path, kind="skill", key="ancillery-skill")
    seen = {}

    def fake_run_task(task_path, skill_path, condition, mock_mcp_url):
        seen["skill_path"] = skill_path
        seen["harness_env"] = os.environ.get("HARNESS_CONFIG_PATH")
        return _FakeEvalResult(score=1.0, passed=True)

    import eval.optimizer.skillopt_adapter as mod
    monkeypatch.setattr(mod, "run_task", fake_run_task)
    items = [{"id": "ancillery-000", "question": "q", "task_type": "ancillery",
              "task_path": str(tmp_path / "tasks" / "ancillery-000")}]
    adapter.rollout(items, "# Candidate Body", str(tmp_path / "roll"))
    assert "candidate_skill" in seen["skill_path"]
    assert seen["harness_env"] is None   # skill target: real harness untouched


def test_setup_installs_prompts(tmp_path, skill_dir, harness_path, monkeypatch):
    """setup() must make reflect's prompt names resolvable (footgun guard)."""
    adapter = _make_adapter(tmp_path, skill_dir, harness_path)
    adapter.setup({"out_root": str(tmp_path / "out"), "env": "travel"})
    import skillopt.gradient.reflect as refl
    assert refl.load_prompt("analyst_error")
    assert refl.load_prompt("analyst_success")


# ── stratified split tests ─────────────────────────────────────────────────────

from eval.optimizer.skillopt_adapter import materialize_stratified_split
import json as _json


def test_stratified_split_distributes_failures_train_and_val(tmp_path):
    items = [{"id": f"t{i:02d}", "question": f"q{i}", "task_type": "d",
              "task_path": f"/x/t{i:02d}"} for i in range(10)]
    split_dir = materialize_stratified_split(
        items, must_split_ids=["t03", "t07"], ratio=(5, 3, 2), seed=7,
        out_dir=tmp_path / "strat")
    splits = {name: _json.loads((split_dir / name / "items.json").read_text())
              for name in ("train", "val", "test")}
    ids = {name: [i["id"] for i in s] for name, s in splits.items()}
    assert "t03" in ids["train"]
    assert "t07" in ids["val"]
    assert not (set(ids["test"]) & {"t03", "t07"})       # never test
    assert len(ids["train"]) == 5 and len(ids["val"]) == 3 and len(ids["test"]) == 2
    # determinism
    split_dir2 = materialize_stratified_split(
        items, must_split_ids=["t03", "t07"], ratio=(5, 3, 2), seed=7,
        out_dir=tmp_path / "strat2")
    ids2 = {name: [i["id"] for i in _json.loads((split_dir2 / name / "items.json").read_text())]
            for name in ("train", "val", "test")}
    assert ids == ids2


def test_stratified_split_single_failure_duplicated_train_and_val(tmp_path):
    items = [{"id": f"t{i:02d}", "question": f"q{i}", "task_type": "d",
              "task_path": f"/x/t{i:02d}"} for i in range(10)]
    split_dir = materialize_stratified_split(
        items, must_split_ids=["t04"], ratio=(5, 3, 2), seed=7,
        out_dir=tmp_path / "lno")
    ids = {name: [i["id"] for i in _json.loads((split_dir / name / "items.json").read_text())]
           for name in ("train", "val", "test")}
    assert "t04" in ids["train"] and "t04" in ids["val"]      # duplicated
    assert "t04" not in ids["test"]
    assert len(ids["train"]) == 5 and len(ids["val"]) == 3 and len(ids["test"]) == 2
    # no other duplication
    non_failure_overlap = (set(ids["train"]) & set(ids["val"])) - {"t04"}
    assert not non_failure_overlap
    manifest = _json.loads((split_dir / "split_manifest.json").read_text())
    assert manifest["duplicated_ids"] == ["t04"]


def test_stratified_split_warns_on_stale_ids(tmp_path):
    items = [{"id": "t00", "question": "q", "task_type": "d", "task_path": "/x"}]
    with pytest.warns(UserWarning, match="stale"):
        materialize_stratified_split(items, must_split_ids=["t00", "ghost-99"],
                                     ratio=(5, 3, 2), seed=7, out_dir=tmp_path / "s")


def test_adapter_setup_uses_stratified_split(tmp_path, skill_dir, harness_path):
    tasks = tmp_path / "tasks"
    for i in range(10):
        _write_task(tasks, f"ancillery-{i:03d}", "ancillery")
    spec = TargetSpec(kind="harness", key="base_system_prompt", skill_path=skill_dir,
                      domain="ancillery", tasks_dir=tasks, harness_config_path=harness_path)
    adapter = TravelEnvAdapter(spec=spec, must_split_ids=["ancillery-002", "ancillery-006"],
                               split_seed=7, seed=7)
    adapter.setup({"out_root": str(tmp_path / "out"), "env": "travel", "seed": 7})
    train_ids = {it["id"] for it in adapter.dataloader.train_items}
    val_ids = {it["id"] for it in adapter.dataloader.val_items}
    test_ids = {it["id"] for it in adapter.dataloader.test_items}
    assert "ancillery-002" in train_ids
    assert "ancillery-006" in val_ids
    assert not (test_ids & {"ancillery-002", "ancillery-006"})
    assert len(train_ids) == 5 and len(val_ids) == 3 and len(test_ids) == 2


def test_rollout_writes_conversation_files(tmp_path, skill_dir, harness_path, monkeypatch):
    """Reflect requires predictions/<id>/conversation.json — rollout must write them."""
    adapter = _make_adapter(tmp_path, skill_dir, harness_path)

    def fake_run_task(task_path, skill_path, condition, mock_mcp_url):
        r = _FakeEvalResult(score=0.0, passed=False, reason="Missing required tools: ['add_ancillary']")
        r.tools_called = []
        r.tool_params = {}
        return r

    import eval.optimizer.skillopt_adapter as mod
    monkeypatch.setattr(mod, "run_task", fake_run_task)
    items = [{"id": "ancillery-000", "question": "Add a window seat", "task_type": "ancillery",
              "task_path": str(tmp_path / "tasks" / "ancillery-000")}]
    adapter.rollout(items, "PROMPT", str(tmp_path / "roll"))
    conv_path = tmp_path / "roll" / "predictions" / "ancillery-000" / "conversation.json"
    assert conv_path.exists()
    conv = _json.loads(conv_path.read_text())
    assert any("Add a window seat" in str(c.get("content", "")) for c in conv)
    assert any("NO tools" in str(c.get("content", "")) for c in conv)
    assert any("FAILED" in str(c.get("content", "")) for c in conv)


# ── strategy_directive tests ──────────────────────────────────────────────────

def test_reflect_strategy_directive_appended_to_error_system(
    tmp_path, skill_dir, harness_path, monkeypatch
):
    """strategy_directive must appear in the error_system kwarg passed to run_minibatch_reflect."""
    from eval.optimizer.skillopt_adapter import TravelEnvAdapter, TargetSpec
    from eval.optimizer.skillopt_prompts import STRATEGY_DIRECTIVES

    tasks = tmp_path / "tasks"
    for i in range(3):
        _write_task(tasks, f"ancillery-{i:03d}", "ancillery")
    spec = TargetSpec(
        kind="harness", key="base_system_prompt", skill_path=skill_dir,
        domain="ancillery", tasks_dir=tasks, harness_config_path=harness_path,
    )
    directive = STRATEGY_DIRECTIVES["push-tool-action"]
    adapter = TravelEnvAdapter(
        spec=spec,
        mock_mcp_url="http://localhost:8000",
        strategy_directive=directive,
    )

    captured = {}

    import eval.optimizer.skillopt_adapter as mod
    original_reflect = mod.run_minibatch_reflect

    def capturing_reflect(**kwargs):
        captured.update(kwargs)
        return []  # stub return

    monkeypatch.setattr(mod, "run_minibatch_reflect", capturing_reflect)
    adapter.reflect(results=[], skill_content="skill text", out_dir=str(tmp_path / "out"))

    assert "error_system" in captured
    error_system = captured["error_system"]
    assert error_system is not None
    assert directive in error_system, (
        f"strategy_directive not found in error_system.\n"
        f"error_system={error_system!r}\n"
        f"directive={directive!r}"
    )


def test_reflect_no_directive_passes_none_or_base_error_system(
    tmp_path, skill_dir, harness_path, monkeypatch
):
    """When strategy_directive is empty, error_system is passed as the base (or None)."""
    from eval.optimizer.skillopt_adapter import TravelEnvAdapter, TargetSpec
    from eval.optimizer.skillopt_prompts import STRATEGY_DIRECTIVES

    tasks = tmp_path / "tasks"
    for i in range(3):
        _write_task(tasks, f"ancillery-{i:03d}", "ancillery")
    spec = TargetSpec(
        kind="harness", key="base_system_prompt", skill_path=skill_dir,
        domain="ancillery", tasks_dir=tasks, harness_config_path=harness_path,
    )
    adapter = TravelEnvAdapter(
        spec=spec,
        mock_mcp_url="http://localhost:8000",
        strategy_directive="",  # empty — no steering
    )

    captured = {}

    import eval.optimizer.skillopt_adapter as mod

    def capturing_reflect(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(mod, "run_minibatch_reflect", capturing_reflect)
    adapter.reflect(results=[], skill_content="skill text", out_dir=str(tmp_path / "out"))

    # error_system should not have been augmented
    error_system = captured.get("error_system")
    # It should NOT contain any STRATEGY_DIRECTIVES content
    for directive in STRATEGY_DIRECTIVES.values():
        assert directive not in (error_system or ""), (
            "strategy_directive should not appear when adapter.strategy_directive is empty"
        )


def test_reflect_directive_not_appended_to_success_system(
    tmp_path, skill_dir, harness_path, monkeypatch
):
    """strategy_directive must only affect error_system, not success_system."""
    from eval.optimizer.skillopt_adapter import TravelEnvAdapter, TargetSpec
    from eval.optimizer.skillopt_prompts import STRATEGY_DIRECTIVES

    tasks = tmp_path / "tasks"
    for i in range(3):
        _write_task(tasks, f"ancillery-{i:03d}", "ancillery")
    spec = TargetSpec(
        kind="harness", key="base_system_prompt", skill_path=skill_dir,
        domain="ancillery", tasks_dir=tasks, harness_config_path=harness_path,
    )
    directive = STRATEGY_DIRECTIVES["simplify"]
    adapter = TravelEnvAdapter(
        spec=spec,
        mock_mcp_url="http://localhost:8000",
        strategy_directive=directive,
    )

    captured = {}

    import eval.optimizer.skillopt_adapter as mod

    def capturing_reflect(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(mod, "run_minibatch_reflect", capturing_reflect)
    adapter.reflect(results=[], skill_content="skill text", out_dir=str(tmp_path / "out"))

    success_system = captured.get("success_system")
    assert directive not in (success_system or ""), (
        "strategy_directive must NOT be injected into success_system"
    )
