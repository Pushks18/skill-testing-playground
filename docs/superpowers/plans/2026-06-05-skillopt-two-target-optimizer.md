# SkillOpt Two-Target Optimizer (Slice 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the propose-only optimization engine that consumes `failure_classification.json` and uses the `skillopt` package's full trainer to improve either a SKILL.md body or one harness-config key, gated on a held-out split.

**Architecture:** A `TravelEnvAdapter(EnvAdapter)` + `TravelTaskLoader(SplitDataLoader)` plug our existing `run_task` eval into skillopt's 6-stage trainer (`ReflACTTrainer`). A driver CLI resolves each failure cluster to a target artifact, runs the trainer with the mixed gate, and writes `*_proposed.*` files plus an honest report. A small refactor adds a `HARNESS_CONFIG_PATH` env override so candidate harness configs can be evaluated without touching the real one.

**Tech Stack:** Python 3.11, `skillopt==0.1.0` (verified on PyPI; internal name "ReflACT"), existing eval stack (`run_task`, mock MCP, gpt-4o-mini via `OPENAI_API_KEY`), pytest.

**Spec:** `docs/superpowers/specs/2026-06-04-skillopt-two-target-optimizer-design.md`

---

## Execution preamble (read first)

- **Repo:** all work in `/Users/pushkaraj/Documents/skill-testing-playground`, commits on main.
- **Python:** plain `python` is NOT on PATH — use `.venv/bin/python` for everything.
- **Commit policy:** imperative (`feat:`/`fix:`/`test:`/`chore:`), NO co-author lines, one commit per task.
- **Working-tree drift warning:** the repo has pre-existing uncommitted modifications (`eval/ab_compare.py`, `eval/cost.py`, `eval/run_task.py`, `eval/gate_check.py`, `ui/app.py`, others). `git add` ONLY the files your task touches — never `git add -A`/`git add .`.
- **skillopt API facts** below were verified against the actual 0.1.0 wheel (extracted package source), not the paper. Where a behavior could not be verified at rest, Task 2 (spike) pins it down and records it in a findings doc that later tasks consume.

### Verified skillopt contracts (from the wheel)

```python
# Trainer
from skillopt.engine.trainer import ReflACTTrainer
ReflACTTrainer(cfg: dict, adapter: EnvAdapter).train()  # cfg is the FLAT dict

# Config: structured YAML → flat dict
from skillopt.config import load_config, flatten_config
# _FLATTEN_MAP (relevant keys):
#   train.num_epochs → num_epochs;  train.steps_per_epoch → steps_per_epoch
#   train.batch_size → batch_size
#   gradient.minibatch_size → minibatch_size
#   optimizer.learning_rate → edit_budget;  optimizer.min_learning_rate → min_edit_budget
#   evaluation.use_gate → use_gate; evaluation.gate_metric → gate_metric
#   evaluation.gate_mixed_weight → gate_mixed_weight
#   env.name → env;  env.skill_init → skill_init;  env.out_root → out_root
#   env.<anything else> → passed through flat

# Dataloader base (skillopt/datasets/base.py)
from skillopt.datasets.base import SplitDataLoader, BatchSpec
SplitDataLoader(split_dir="", data_path="", split_mode="ratio",
                split_ratio="2:1:7",   # ORDER: train:val:test
                split_seed=42, split_output_dir="", seed=42, limit=0)
# subclass overrides load_raw_items(data_path) -> list[dict]; items need "id"
# ratio mode materializes splits under out_root/_generated_splits/... deterministically

# Adapter base (skillopt/envs/base.py) — copy the SearchQA adapter shape:
#   build_env_from_batch(batch, **kw) -> list(batch.payload or [])   (env manager IS the item list)
#   build_train_env(batch_size, seed, **kw) / build_eval_env(env_num, split, seed, **kw)
#       -> dataloader.build_*_batch(...) then build_env_from_batch
#   rollout(env_manager, skill_content, out_dir, **kw) -> list[dict]
#       required keys per item: id:str, hard:int(0/1), soft:float(0..1)
#       useful: fail_reason, task_type, question
#   reflect(results, skill_content, out_dir, **kw) -> delegate to
#       skillopt.gradient.reflect.run_minibatch_reflect(
#           results=..., skill_content=..., prediction_dir=..., patches_dir=...,
#           workers=..., failure_only=..., minibatch_size=..., edit_budget=...,
#           random_seed=kw.get("random_seed"),
#           error_system=self.get_error_minibatch_prompt(),    # base-class hook, None = default prompt
#           success_system=self.get_success_minibatch_prompt(),
#           step_buffer_context=kw.get("step_buffer_context",""),
#           meta_skill_context=kw.get("meta_skill_context",""),
#           update_mode=getattr(self,"_cfg",{}).get("skill_update_mode","patch"))
#   get_task_types() -> list[str];  requires_ray() -> False
# Reference implementation to imitate: skillopt/envs/searchqa/adapter.py

# Gate (skillopt/evaluation/gate.py): gate_metric ∈ {"hard","soft","mixed"}, mixed_weight
# Model backends (skillopt/model/common.py): backend "openai_chat" works with OPENAI_API_KEY
```

### File map

| File | Responsibility |
|------|---------------|
| `eval/optimizer/skillopt_adapter.py` (create) | `TargetSpec`, artifact materialization, `TravelTaskLoader`, `TravelEnvAdapter` |
| `eval/optimizer/optimize.py` (create) | driver CLI: clusters → trainer → proposed files + report |
| `eval/optimizer/skillopt_config.yaml` (create) | trainer config (mixed gate, epochs, edit budget, backends) |
| `agent/travel_agent.py` (modify) | `HARNESS_CONFIG_PATH` env-var resolution in `load_harness_config` |
| `tests/test_skillopt_adapter.py` (create) | TargetSpec/materialization/loader/rollout tests (run_task stubbed) |
| `tests/test_optimize_driver.py` (create) | target resolution, whitelist, report, dry-run tests |
| `tests/test_skillopt_spike.py` (create) | no-LLM end-to-end trainer integration test (slow-marked) |
| `docs/superpowers/specs/skillopt-spike-findings.md` (create, Task 2) | pinned-down trainer behaviors later tasks consume |

---

### Task 1: `HARNESS_CONFIG_PATH` override + skillopt dependency

**Files:**
- Modify: `agent/travel_agent.py` (load_harness_config + its two call sites)
- Modify: `requirements.txt` (or `pyproject.toml` if that's where deps live — check both, add where the other eval deps are)
- Test: `tests/test_harness_config.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_harness_config.py`:

```python
def test_env_var_overrides_default_path(tmp_path, monkeypatch):
    """HARNESS_CONFIG_PATH redirects load_harness_config when no explicit arg."""
    from agent.travel_agent import load_harness_config
    p = tmp_path / "override.yaml"
    p.write_text('base_system_prompt: "ENV OVERRIDE PROMPT"\n')
    monkeypatch.setenv("HARNESS_CONFIG_PATH", str(p))
    cfg = load_harness_config()
    assert cfg["base_system_prompt"] == "ENV OVERRIDE PROMPT"


def test_explicit_arg_beats_env_var(tmp_path, monkeypatch):
    from agent.travel_agent import load_harness_config
    env_p = tmp_path / "env.yaml"
    env_p.write_text('base_system_prompt: "FROM ENV"\n')
    arg_p = tmp_path / "arg.yaml"
    arg_p.write_text('base_system_prompt: "FROM ARG"\n')
    monkeypatch.setenv("HARNESS_CONFIG_PATH", str(env_p))
    cfg = load_harness_config(config_path=arg_p)
    assert cfg["base_system_prompt"] == "FROM ARG"


def test_no_env_var_uses_default(monkeypatch):
    from agent.travel_agent import load_harness_config, HARNESS_DEFAULTS
    monkeypatch.delenv("HARNESS_CONFIG_PATH", raising=False)
    cfg = load_harness_config()
    # default file on disk == defaults (verbatim externalization)
    assert cfg["base_system_prompt"] == HARNESS_DEFAULTS["base_system_prompt"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_harness_config.py -v -k "env_var or explicit_arg or no_env"`
Expected: `test_env_var_overrides_default_path` FAILS (env var ignored today). The other two may pass already — fine, they pin the contract.

- [ ] **Step 3: Implement** — in `agent/travel_agent.py`:

Change the signature and resolution of `load_harness_config`:

```python
def load_harness_config(config_path: pathlib.Path | None = None) -> dict:
    """Load harness config from YAML, falling back to HARNESS_DEFAULTS per key.

    Path resolution: explicit argument → HARNESS_CONFIG_PATH env var → default
    file next to this module. The env var lets the optimizer evaluate candidate
    configs without touching the real one.
    """
    if config_path is None:
        env_override = os.environ.get("HARNESS_CONFIG_PATH")
        config_path = pathlib.Path(env_override) if env_override else _CONFIG_PATH
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in HARNESS_DEFAULTS.items()}
    if config_path.exists():
        try:
            loaded = yaml.safe_load(config_path.read_text()) or {}
        except yaml.YAMLError as e:
            warnings.warn(f"harness_config parse error, using defaults: {e}")
            loaded = {}
        for key in HARNESS_DEFAULTS:
            if key in loaded and loaded[key] is not None:
                cfg[key] = loaded[key]
    return cfg
```

Then update the two call sites so the env var takes effect at call time:
- in `make_mcp_tools`: `descriptions = load_harness_config()["tool_descriptions"]`
- in `build_travel_agent`: `config = load_harness_config()`

(The existing test `test_build_agent_uses_config_prompt` monkeypatches `ta._CONFIG_PATH`; the no-arg path reads the module global at call time, so it still works.)

- [ ] **Step 4: Add the dependency**

Check where deps are declared: `grep -l "langgraph\|httpx" requirements.txt pyproject.toml 2>/dev/null`. Add `skillopt>=0.1.0` there, then install: `.venv/bin/pip install "skillopt>=0.1.0"`. Verify: `.venv/bin/python -c "import skillopt; print(skillopt.__version__)"` → `0.1.0`.

- [ ] **Step 5: Run the full harness + adjacent suites**

Run: `.venv/bin/python -m pytest tests/test_harness_config.py tests/test_classify_failures.py -v`
Expected: all pass (10 harness + 15 classify).

- [ ] **Step 6: Commit**

```bash
git add agent/travel_agent.py tests/test_harness_config.py requirements.txt  # or pyproject.toml
git commit -m "feat: add HARNESS_CONFIG_PATH override and skillopt dependency"
```

---

### Task 2: Integration spike — pin down trainer behaviors (no LLM, no API cost)

**Purpose:** skillopt is v0.1.0; four behaviors could not be verified from source reading alone. This task runs the REAL `ReflACTTrainer` end-to-end with a stub adapter (canned rollout scores, canned patches, no LLM calls) and records findings. **Later tasks depend on the findings doc.**

**Files:**
- Create: `tests/test_skillopt_spike.py`
- Create: `docs/superpowers/specs/skillopt-spike-findings.md`

- [ ] **Step 1: Write the spike test**

Create `tests/test_skillopt_spike.py`:

```python
# tests/test_skillopt_spike.py
"""Integration spike: drive the real ReflACTTrainer with a stub adapter.

No LLM calls, no API cost. Pins down v0.1.0 behaviors that later code
depends on: skill_init semantics, train() return shape, where the best
artifact is persisted, and whether empty reflect patches are tolerated.
Findings recorded in docs/superpowers/specs/skillopt-spike-findings.md.
"""
import json
import pathlib

import pytest

from skillopt.datasets.base import SplitDataLoader, BatchSpec
from skillopt.envs.base import EnvAdapter


class StubLoader(SplitDataLoader):
    """10 synthetic items, ratio-split 5:3:2."""

    def load_raw_items(self, data_path):
        return [{"id": f"stub-{i:03d}", "question": f"question {i}", "task_type": "stub"}
                for i in range(10)]


class StubAdapter(EnvAdapter):
    """Scores improve when the skill text contains the token IMPROVED."""

    def __init__(self, **kw):
        self.dataloader = StubLoader(data_path="unused", split_mode="ratio",
                                     split_ratio="5:3:2", split_seed=7, seed=7)
        self.rollout_calls = []

    def setup(self, cfg):
        super().setup(cfg)
        self.dataloader.setup(cfg)

    def get_dataloader(self):
        return self.dataloader

    def build_env_from_batch(self, batch: BatchSpec, **kw):
        return list(batch.payload or [])

    def build_train_env(self, batch_size, seed, **kw):
        return self.build_env_from_batch(
            self.dataloader.build_train_batch(batch_size=batch_size, seed=seed, **kw), **kw)

    def build_eval_env(self, env_num, split, seed, **kw):
        return self.build_env_from_batch(
            self.dataloader.build_eval_batch(env_num=env_num, split=split, seed=seed, **kw), **kw)

    def rollout(self, env_manager, skill_content, out_dir, **kw):
        self.rollout_calls.append({"n_items": len(env_manager), "out_dir": out_dir})
        good = "IMPROVED" in (skill_content or "")
        return [{"id": it["id"], "hard": 1 if good else 0,
                 "soft": 0.9 if good else 0.2,
                 "fail_reason": "" if good else "stub failure",
                 "task_type": "stub"} for it in env_manager]

    def reflect(self, results, skill_content, out_dir, **kw):
        # Canned patch in skillopt's RawPatch dict shape — one bounded edit
        # appending the magic token. If the trainer rejects this shape, the
        # error message tells us the real contract (record it!).
        return [{
            "edits": [{"op": "add", "content": "\nIMPROVED: always call the required tool."}],
            "summary": "stub patch",
        }]

    def get_task_types(self):
        return ["stub"]


@pytest.mark.slow
def test_trainer_end_to_end_with_stub(tmp_path):
    from skillopt.engine.trainer import ReflACTTrainer

    out_root = tmp_path / "spike_out"
    cfg = {
        # flat config (legacy format accepted per skillopt.config docstring)
        "env": "travel-stub",
        "out_root": str(out_root),
        "skill_init": "Initial skill text. Step 1: do the task.",
        "num_epochs": 1,
        "steps_per_epoch": 1,
        "batch_size": 5,
        "edit_budget": 3,
        "use_gate": True,
        "gate_metric": "mixed",
        "gate_mixed_weight": 0.5,
        "seed": 7,
    }
    adapter = StubAdapter()
    trainer = ReflACTTrainer(cfg, adapter)
    result = trainer.train()

    # ── Findings to record (print everything; assertions stay minimal) ──
    print("train() returned:", type(result), result)
    print("rollout calls:", adapter.rollout_calls)
    print("out_root contents:")
    for p in sorted(out_root.rglob("*")):
        print("  ", p.relative_to(out_root))

    assert adapter.rollout_calls, "trainer never called rollout"
    assert out_root.exists()
```

- [ ] **Step 2: Run the spike**

Run: `.venv/bin/python -m pytest tests/test_skillopt_spike.py -v -s 2>&1 | tee /tmp/spike_output.txt`

This is exploratory — the FIRST run may fail on a cfg-shape or patch-shape mismatch. That is the point. Iterate on the stub (NOT on assumptions) until the trainer completes one epoch. Budget: if after ~10 focused iterations the trainer cannot complete an epoch due to fundamental contract mismatch (e.g., it hard-requires a model backend call you cannot stub), STOP and report BLOCKED — the pre-approved fallback is gate+types-only integration, and that is a controller/user decision, not yours.

Likely required adjustments you are ALLOWED to make: cfg key names (check `skillopt/config.py` `_FLATTEN_MAP` and trainer's cfg reads), RawPatch dict shape (check `skillopt/types.py` `RawPatch.from_dict`), reflect return wrapping, skill_init as path-vs-text, model-backend stub via cfg (`model_backend: "openai_chat"` plus monkeypatched `skillopt.model` call if the trainer's aggregate/select stages insist on an LLM — try `minibatch_size`/`merge_batch_size` settings or patch `skillopt.gradient.aggregate` entry point with a passthrough).

- [ ] **Step 3: Record findings**

Create `docs/superpowers/specs/skillopt-spike-findings.md` answering, with evidence from the run:

```markdown
# SkillOpt 0.1.0 spike findings (Task 2)

1. **skill_init semantics:** text literal or file path? → [ANSWER + evidence]
2. **train() return value:** type and keys → [ANSWER]
3. **Best-artifact location:** where under out_root does the accepted/best
   skill text live (exact relative path / history.json key)? → [ANSWER]
4. **Final test-split evaluation:** does the trainer run split="test" itself,
   or must the driver do it after train()? → [ANSWER]
5. **RawPatch dict shape accepted by reflect→aggregate:** → [exact dict shape]
6. **LLM dependence of aggregate/select stages with a 1-patch reflect:** did any
   stage require a live model? what cfg/stub made it work? → [ANSWER]
7. **cfg keys actually consumed** (the working flat cfg from the spike, verbatim) → [paste]
8. **Anything surprising** → [notes]
```

Fill in every ANSWER from observed behavior, not source-reading guesses.

- [ ] **Step 4: Stabilize the test** — once green, keep assertions minimal (rollout called, out_root populated, plus whatever the findings make safe to assert — e.g. best artifact contains "IMPROVED" if the gate accepted). Register the `slow` marker if not present: check `pytest.ini`/`pyproject.toml` for `markers`; add `slow: long-running integration tests` if missing.

- [ ] **Step 5: Run full suite to confirm nothing broke**

Run: `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_mock_mcp.py 2>&1 | tail -5`

- [ ] **Step 6: Commit**

```bash
git add tests/test_skillopt_spike.py docs/superpowers/specs/skillopt-spike-findings.md
# plus pytest.ini/pyproject.toml if you registered the marker
git commit -m "test: add skillopt trainer integration spike with findings doc"
```

---

### Task 3: `TargetSpec` + artifact materialization

**Files:**
- Create: `eval/optimizer/skillopt_adapter.py` (first part)
- Create: `tests/test_skillopt_adapter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skillopt_adapter.py`:

```python
# tests/test_skillopt_adapter.py
import pathlib

import pytest
import yaml

from eval.optimizer.skillopt_adapter import (
    TargetSpec, initial_artifact, materialize_candidate,
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_skillopt_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.optimizer.skillopt_adapter'`

- [ ] **Step 3: Implement**

Create `eval/optimizer/skillopt_adapter.py`:

```python
# eval/optimizer/skillopt_adapter.py
"""SkillOpt integration: two-target adapter for the travel eval.

TargetSpec describes WHAT is being optimized (a SKILL.md body, or one
optimizable key of agent/harness_config.yaml). TravelTaskLoader feeds the
domain's tasks through skillopt's deterministic ratio split. TravelEnvAdapter
plugs run_task into the ReflACT trainer's rollout/reflect stages.

Propose-only: nothing here writes to skills/ or agent/harness_config.yaml.
"""
from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass
from typing import Literal, Optional

import yaml

from eval.skill_loader import load_skill


@dataclass
class TargetSpec:
    """What the optimizer is editing, and the context to evaluate candidates."""
    kind: Literal["skill", "harness"]
    key: str                      # harness: config key; skill: skill name
    skill_path: pathlib.Path      # skill injected during rollout (source skill for kind=skill)
    domain: str
    tasks_dir: pathlib.Path
    harness_config_path: pathlib.Path


@dataclass
class CandidateContext:
    """Where a materialized candidate lives for one rollout."""
    skill_path: pathlib.Path                       # skill dir to inject
    harness_config_path: Optional[pathlib.Path]    # set only for harness targets


def initial_artifact(spec: TargetSpec) -> str:
    """The current text of the artifact under optimization."""
    if spec.kind == "skill":
        skill = load_skill(spec.skill_path)
        if skill is None:
            raise FileNotFoundError(f"no SKILL.md under {spec.skill_path}")
        return skill.body
    config = yaml.safe_load(spec.harness_config_path.read_text())
    value = config[spec.key]
    if isinstance(value, dict):
        return yaml.safe_dump(value, sort_keys=False)
    return str(value)


def _skill_frontmatter(skill_path: pathlib.Path) -> str:
    """Raw frontmatter block (--- ... ---) of the source SKILL.md."""
    content = (skill_path / "SKILL.md").read_text()
    m = re.match(r"^(---\n.*?\n---\n)", content, re.DOTALL)
    return m.group(1) if m else ""


def materialize_candidate(
    spec: TargetSpec,
    artifact_text: str,
    out_dir: pathlib.Path,
) -> CandidateContext:
    """Write a candidate artifact to disk, ready for rollout.

    skill target  → temp skill dir with original frontmatter + candidate body
    harness target → full config copy with the one key substituted
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if spec.kind == "skill":
        candidate_dir = out_dir / "candidate_skill"
        candidate_dir.mkdir(exist_ok=True)
        frontmatter = _skill_frontmatter(spec.skill_path)
        (candidate_dir / "SKILL.md").write_text(f"{frontmatter}\n{artifact_text.strip()}\n")
        return CandidateContext(skill_path=candidate_dir, harness_config_path=None)

    # harness target
    config = yaml.safe_load(spec.harness_config_path.read_text())
    current = config[spec.key]
    if isinstance(current, dict):
        try:
            new_value = yaml.safe_load(artifact_text)
        except yaml.YAMLError as e:
            raise ValueError(f"candidate artifact is not valid YAML for key "
                             f"{spec.key!r}: {e}") from e
        if not isinstance(new_value, dict):
            raise ValueError(f"candidate artifact is not valid YAML mapping for key {spec.key!r}")
        config[spec.key] = new_value
    else:
        config[spec.key] = artifact_text
    candidate_path = out_dir / "candidate_harness_config.yaml"
    candidate_path.write_text(yaml.safe_dump(config, sort_keys=False))
    return CandidateContext(skill_path=spec.skill_path, harness_config_path=candidate_path)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_skillopt_adapter.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add eval/optimizer/skillopt_adapter.py tests/test_skillopt_adapter.py
git commit -m "feat: add TargetSpec and two-target artifact materialization"
```

---

### Task 4: `TravelTaskLoader`

**Files:**
- Modify: `eval/optimizer/skillopt_adapter.py` (append)
- Modify: `tests/test_skillopt_adapter.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_skillopt_adapter.py`:

```python
from eval.optimizer.skillopt_adapter import TravelTaskLoader


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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_skillopt_adapter.py -v -k loader`
Expected: ImportError

- [ ] **Step 3: Implement** — append to `eval/optimizer/skillopt_adapter.py`:

```python
from skillopt.datasets.base import BatchSpec, SplitDataLoader


class TravelTaskLoader(SplitDataLoader):
    """Feeds one domain's tasks/ dirs through skillopt's ratio split (train:val:test)."""

    def __init__(self, tasks_dir: pathlib.Path, domain: str, **kwargs):
        kwargs.setdefault("split_mode", "ratio")
        kwargs.setdefault("split_ratio", "5:3:2")
        super().__init__(data_path=str(tasks_dir), **kwargs)
        self.tasks_dir = pathlib.Path(tasks_dir)
        self.domain = domain

    def load_raw_items(self, data_path: str) -> list[dict]:
        items: list[dict] = []
        for task_dir in sorted(pathlib.Path(data_path).iterdir()):
            toml_path = task_dir / "task.toml"
            instr_path = task_dir / "instruction.md"
            if not (toml_path.exists() and instr_path.exists()):
                continue
            m = re.search(r'^domain\s*=\s*"([^"]+)"', toml_path.read_text(), re.MULTILINE)
            if not m or m.group(1) != self.domain:
                continue
            items.append({
                "id": task_dir.name,
                "question": instr_path.read_text().strip()[:300],
                "task_type": self.domain,
                "task_path": str(task_dir),
            })
        return items
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_skillopt_adapter.py -v`
Expected: 9 PASS

- [ ] **Step 5: Commit**

```bash
git add eval/optimizer/skillopt_adapter.py tests/test_skillopt_adapter.py
git commit -m "feat: add TravelTaskLoader with domain filtering and ratio split"
```

---

### Task 4b: Replacement prompts module (REQUIRED — added after spike findings)

**Why:** the skillopt 0.1.0 wheel ships ZERO `.md` prompt files — `load_prompt(name)` raises `FileNotFoundError` for every prompt. The aggregate stage calls it unconditionally (`merge_failure`/`merge_success`/`merge_final` in patch mode), reflect falls back to it when `error_system`/`success_system` are None, and clip uses it when edits exceed budget. Production runs WILL crash without replacements. (Spike findings §6.)

**Files:**
- Create: `eval/optimizer/skillopt_prompts.py`
- Modify: `tests/test_skillopt_adapter.py` (append)

- [ ] **Step 1: Read the parsers to learn the required output format.** Before writing any prompt text, read in `.venv/lib/python3.11/site-packages/skillopt/`:
  - `gradient/reflect.py` — how the optimizer model's reflect output is parsed into a patch (look for the JSON extraction / expected keys: `edits` with `op`/`content`/`target`, per spike findings §5)
  - `gradient/aggregate.py` — what `merge_*` prompts must make the model return (merged patch JSON)
  - `optimizer/clip.py` — what the rank/clip prompt must return
  Your prompt texts MUST instruct the model to output exactly the JSON those parsers extract.

- [ ] **Step 2: Implement `eval/optimizer/skillopt_prompts.py`:**

```python
# eval/optimizer/skillopt_prompts.py
"""Replacement prompts for skillopt 0.1.0 (the wheel ships no .md prompt files).

install_prompts() patches load_prompt at every consuming module so the
trainer's reflect/aggregate/clip stages get functional prompt text. Texts
are written against the actual parsers in skillopt.gradient/optimizer —
the model must emit the JSON shapes those parsers extract.
"""
from __future__ import annotations

# name → prompt text. Cover every name reachable with our config
# (update_mode="patch"): reflect minibatch prompts, merge_{failure,success,final},
# clip/rank, plus slow_update/meta_skill in case those stages are enabled later.
PROMPTS: dict[str, str] = {
    "error_minibatch": "...",        # written in Step 2 against the reflect parser
    "success_minibatch": "...",
    "merge_failure": "...",
    "merge_success": "...",
    "merge_final": "...",
    # clip.py's prompt_name — confirm exact name from optimizer/clip.py
    # slow_update / meta_skill / lr_autonomous — include defensively
}


def install_prompts() -> None:
    """Route skillopt's load_prompt through PROMPTS, falling back to the original."""
    import skillopt.prompts as sp
    original = sp.load_prompt

    def patched(name: str, env: str | None = None) -> str:
        if name in PROMPTS:
            return PROMPTS[name]
        return original(name, env)

    import skillopt.gradient.aggregate as agg
    import skillopt.gradient.reflect as refl
    import skillopt.optimizer.clip as clip
    import skillopt.optimizer.slow_update as slow
    import skillopt.optimizer.meta_skill as meta
    for module in (sp, agg, refl, clip, slow, meta):
        module.load_prompt = patched
```

(The `"..."` placeholders above are filled IN THIS TASK from Step 1's parser reading — they are not optional. Each prompt must state the role, the failure/success trajectory context it receives, and demand the exact JSON output shape with `edits: [{op, content, target}]` etc.)

- [ ] **Step 3: Test** — append to `tests/test_skillopt_adapter.py`:

```python
def test_install_prompts_covers_reachable_names():
    from eval.optimizer.skillopt_prompts import PROMPTS, install_prompts
    install_prompts()
    import skillopt.gradient.aggregate as agg
    # every name aggregate requests in patch mode resolves without FileNotFoundError
    for name in ("merge_failure", "merge_success", "merge_final"):
        assert agg.load_prompt(name)
    # all prompt texts demand JSON edits output
    for name, text in PROMPTS.items():
        assert "edits" in text or "JSON" in text, f"prompt {name!r} lacks output-format instruction"
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_skillopt_adapter.py -v -k prompts` → PASS

- [ ] **Step 5: Commit**

```bash
git add eval/optimizer/skillopt_prompts.py tests/test_skillopt_adapter.py
git commit -m "feat: add replacement prompts for stripped skillopt distribution"
```

---

### Task 5: `TravelEnvAdapter` — rollout + reflect

**Files:**
- Modify: `eval/optimizer/skillopt_adapter.py` (append)
- Modify: `tests/test_skillopt_adapter.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_skillopt_adapter.py`:

```python
from eval.optimizer.skillopt_adapter import TravelEnvAdapter


class _FakeEvalResult:
    def __init__(self, score, passed, reason=""):
        self.score = score
        self.passed_verifier = passed
        self.judge_reasoning = reason


def _make_adapter(tmp_path, skill_dir, harness_path, kind="harness", key="base_system_prompt"):
    tasks = tmp_path / "tasks"
    for i in range(3):
        _write_task(tasks, f"ancillery-{i:03d}", "ancillery")
    spec = TargetSpec(kind=kind, key=key, skill_path=skill_dir, domain="ancillery",
                      tasks_dir=tasks, harness_config_path=harness_path)
    return TravelEnvAdapter(spec=spec, mock_mcp_url="http://localhost:8000")


def test_rollout_shapes_results(tmp_path, skill_dir, harness_path, monkeypatch):
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_skillopt_adapter.py -v -k "rollout"`
Expected: ImportError (TravelEnvAdapter)

- [ ] **Step 3: Implement** — append to `eval/optimizer/skillopt_adapter.py`:

```python
import json

from skillopt.envs.base import EnvAdapter
from skillopt.gradient.reflect import run_minibatch_reflect

from eval.run_task import run_task


class TravelEnvAdapter(EnvAdapter):
    """ReflACT adapter: rollout = run_task on the split's tasks, with the
    candidate artifact materialized per TargetSpec."""

    def __init__(
        self,
        spec: TargetSpec,
        mock_mcp_url: str = "http://localhost:8000",
        workers: int = 4,
        failure_only: bool = True,
        minibatch_size: int = 4,
        edit_budget: int = 3,
        **kwargs,
    ):
        self.spec = spec
        self.mock_mcp_url = mock_mcp_url
        self.workers = workers
        self.failure_only = failure_only
        self.minibatch_size = minibatch_size
        self.edit_budget = edit_budget
        self.dataloader = TravelTaskLoader(
            tasks_dir=spec.tasks_dir, domain=spec.domain, **kwargs)

    # ── trainer lifecycle (mirrors skillopt's SearchQA reference adapter) ──

    def setup(self, cfg: dict) -> None:
        super().setup(cfg)
        self.dataloader.setup(cfg)

    def get_dataloader(self):
        return self.dataloader

    def build_env_from_batch(self, batch: BatchSpec, **kwargs):
        return list(batch.payload or [])

    def build_train_env(self, batch_size: int, seed: int, **kwargs):
        batch = self.dataloader.build_train_batch(batch_size=batch_size, seed=seed, **kwargs)
        return self.build_env_from_batch(batch, **kwargs)

    def build_eval_env(self, env_num: int, split: str, seed: int, **kwargs):
        batch = self.dataloader.build_eval_batch(env_num=env_num, split=split, seed=seed, **kwargs)
        return self.build_env_from_batch(batch, **kwargs)

    # ── rollout: the real eval ─────────────────────────────────────────────

    def rollout(self, env_manager, skill_content: str, out_dir: str, **kwargs) -> list[dict]:
        items: list[dict] = env_manager
        out_path = pathlib.Path(out_dir)
        ctx = materialize_candidate(self.spec, skill_content, out_path)

        previous = os.environ.get("HARNESS_CONFIG_PATH")
        results: list[dict] = []
        try:
            if ctx.harness_config_path is not None:
                os.environ["HARNESS_CONFIG_PATH"] = str(ctx.harness_config_path)
            for item in items:
                r = run_task(item["task_path"], str(ctx.skill_path),
                             "with_skill", self.mock_mcp_url)
                results.append({
                    "id": item["id"],
                    "hard": int(r.passed_verifier),
                    "soft": float(r.score),
                    "fail_reason": r.judge_reasoning or "",
                    "task_type": self.spec.domain,
                    "question": item.get("question", ""),
                })
        finally:
            if previous is None:
                os.environ.pop("HARNESS_CONFIG_PATH", None)
            else:
                os.environ["HARNESS_CONFIG_PATH"] = previous

        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "rollout_results.json").write_text(json.dumps(results, indent=2))
        return results

    # ── reflect: delegate to skillopt's native machinery ───────────────────

    def reflect(self, results: list[dict], skill_content: str, out_dir: str, **kwargs):
        prediction_dir = kwargs.get("prediction_dir", os.path.join(out_dir, "predictions"))
        patches_dir = kwargs.get("patches_dir", os.path.join(out_dir, "patches"))
        return run_minibatch_reflect(
            results=results,
            skill_content=skill_content,
            prediction_dir=prediction_dir,
            patches_dir=patches_dir,
            workers=self.workers,
            failure_only=self.failure_only,
            minibatch_size=self.minibatch_size,
            edit_budget=self.edit_budget,
            random_seed=kwargs.get("random_seed"),
            error_system=self.get_error_minibatch_prompt(),
            success_system=self.get_success_minibatch_prompt(),
            step_buffer_context=kwargs.get("step_buffer_context", ""),
            meta_skill_context=kwargs.get("meta_skill_context", ""),
            update_mode=getattr(self, "_cfg", {}).get("skill_update_mode", "patch"),
        )

    def get_task_types(self) -> list[str]:
        return [self.spec.domain]
```

NOTE: if the Task 2 spike findings recorded a different reflect/cfg contract than the SearchQA template above, FOLLOW THE FINDINGS — they are observed behavior.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_skillopt_adapter.py -v`
Expected: 12 PASS

- [ ] **Step 5: Commit**

```bash
git add eval/optimizer/skillopt_adapter.py tests/test_skillopt_adapter.py
git commit -m "feat: add TravelEnvAdapter with run_task rollout and reflect delegation"
```

---

### Task 6: Trainer config file

**Files:**
- Create: `eval/optimizer/skillopt_config.yaml`

- [ ] **Step 1: Create the config** — structured format; keys verified against `skillopt.config._FLATTEN_MAP` and adjusted per the Task 2 spike findings (the spike's working cfg in findings §7 is authoritative; reconcile before committing):

Per spike findings §7 (the authoritative working cfg), the flat keys the trainer requires include `optimizer_model`, `target_model`, `accumulation`, `merge_batch_size`, `analyst_workers`, `sel_env_num`, `test_env_num`, `eval_test`; `steps_per_epoch` is computed by the trainer and ignored if set (findings §8.1); `use_gate=False` raises (§8.5).

```yaml
# eval/optimizer/skillopt_config.yaml
# Trainer config for the two-target optimizer. The driver overrides env.*
# per run (out_root, skill_init — skill_init MUST be a file path, findings §1).
# gate_metric MUST stay mixed/soft — the hard gate rejects every candidate
# at <=10-task selection scale.

model:
  backend: openai_chat
  optimizer: gpt-4o            # optimizer-side LLM (reflect/aggregate/select)
  target: gpt-4o-mini          # required key; unused (our adapter owns rollout)

train:
  num_epochs: 5
  batch_size: 5                # = train split size (5:3:2 of 10)
  accumulation: 1

gradient:
  minibatch_size: 4
  merge_batch_size: 8

optimizer:
  learning_rate: 3             # flattens to edit_budget: max accepted edits/epoch

evaluation:
  use_gate: true               # mandatory — false raises ValueError
  gate_metric: mixed
  gate_mixed_weight: 0.5

env:
  name: travel
  analyst_workers: 4
  sel_env_num: 3               # selection (val) split size
  test_env_num: 2              # held-out test split size
  eval_test: true              # trainer runs final test itself (findings §4)
  # out_root and skill_init injected by the driver per run
```

- [ ] **Step 2: Verify it loads and flattens**

Run: `.venv/bin/python -c "from skillopt.config import load_config, flatten_config; import json; print(json.dumps(flatten_config(load_config('eval/optimizer/skillopt_config.yaml')), indent=2))"`
Expected: flat dict with `num_epochs: 5`, `edit_budget: 3`, `gate_metric: "mixed"`, `env: "travel"`, no errors.

- [ ] **Step 3: Commit**

```bash
git add eval/optimizer/skillopt_config.yaml
git commit -m "feat: add skillopt trainer config with mixed gate"
```

---

### Task 7: Driver — `eval/optimizer/optimize.py`

**Files:**
- Create: `eval/optimizer/optimize.py`
- Create: `tests/test_optimize_driver.py`

The driver consumes the Task 2 findings for: skill_init semantics, best-artifact location after `train()`, and whether the trainer already evaluates split="test" (findings §1, §3, §4). The code below marks those three integration points — implement them per the findings doc, which is observed behavior.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_optimize_driver.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_optimize_driver.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: Implement**

Create `eval/optimizer/optimize.py`:

```python
# eval/optimizer/optimize.py
"""Two-target optimization driver (Slice 3): cluster → SkillOpt trainer → proposal.

Reads failure_classification.json (Slice 1), resolves each qualifying cluster
to a target artifact (SKILL.md body or one harness-config key), runs the
ReflACT trainer with the mixed gate, and writes *_proposed.* files plus an
optimization_report.json under eval/optimizer_output/.

PROPOSE-ONLY. Never writes to skills/ or agent/harness_config.yaml, never
commits, never opens PRs. A human reviews every proposal.

Usage:
    python -m eval.optimizer.optimize --classification failure_classification.json
    python -m eval.optimizer.optimize --cluster 0 --dry-run
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys

import httpx
import yaml

from eval.optimizer.skillopt_adapter import (
    TargetSpec, TravelEnvAdapter, initial_artifact, materialize_candidate,
    _skill_frontmatter,
)

DEFAULT_TASKS_DIR = pathlib.Path("tasks")
DEFAULT_HARNESS_CONFIG = pathlib.Path("agent/harness_config.yaml")
DEFAULT_SKILLS_ROOT = pathlib.Path("../travel-agent-skills/skills")
OUTPUT_ROOT = pathlib.Path("eval/optimizer_output")


# ── cluster → target resolution ─────────────────────────────────────────────

def resolve_target(cluster: dict, optimizable: list[str] | None = None) -> tuple[str, str]:
    """('harness'|'skill', key). Harness keys checked against the whitelist."""
    target = cluster["target_artifact"]
    if "::" in target:                      # agent/harness_config.yaml::<key>
        key = target.split("::", 1)[1]
        if optimizable is not None:
            roots = {entry.split(".")[0] for entry in optimizable}
            if key.split(".")[0] not in roots:
                raise ValueError(f"harness key {key!r} is not optimizable "
                                 f"(whitelist: {optimizable})")
        return "harness", key
    # skills/<name>/SKILL.md
    parts = pathlib.PurePosixPath(target).parts
    return "skill", parts[parts.index("skills") + 1]


def qualifying_clusters(clusters: list[dict]) -> list[dict]:
    """Harness clusters qualify at n>=1; skill clusters need n>=2 (too thin below)."""
    out = []
    for c in clusters:
        n = c.get("n_failures", len(c.get("task_ids", [])))
        if c["layer"].startswith("harness:") and n >= 1:
            out.append(c)
        elif c["layer"].startswith("skill:") and n >= 2:
            out.append(c)
    return out


def estimate_rollout_calls(n_train: int, n_selection: int, n_test: int, epochs: int) -> int:
    """baseline(selection) + per-epoch (train rollout + selection eval)
    + eval_test runs the test split twice (baseline + best). Findings §8.2-8.3."""
    return n_selection + epochs * (n_train + n_selection) + 2 * n_test


# ── proposal output ──────────────────────────────────────────────────────────

def write_proposed(
    *,
    kind: str,
    key: str,
    artifact_text: str,
    out_dir: pathlib.Path,
    harness_config_path: pathlib.Path | None,
    skill_path: pathlib.Path | None,
) -> pathlib.Path:
    """Write the proposed artifact file. Sources are never modified."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if kind == "harness":
        config = yaml.safe_load(harness_config_path.read_text())
        current = config[key]
        config[key] = yaml.safe_load(artifact_text) if isinstance(current, dict) else artifact_text
        out_path = out_dir / "harness_config_proposed.yaml"
        out_path.write_text(yaml.safe_dump(config, sort_keys=False))
        return out_path
    frontmatter = _skill_frontmatter(skill_path)
    out_path = out_dir / "SKILL_proposed.md"
    out_path.write_text(f"{frontmatter}\n{artifact_text.strip()}\n")
    return out_path


# ── preflight ────────────────────────────────────────────────────────────────

def preflight(mock_mcp_url: str) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("preflight: OPENAI_API_KEY is not set")
    try:
        httpx.get(mock_mcp_url, timeout=3)
    except httpx.ConnectError:
        sys.exit(f"preflight: mock MCP server not reachable at {mock_mcp_url} — "
                 "start it: .venv/bin/python eval/mock_mcp/server.py &")


# ── per-cluster run ──────────────────────────────────────────────────────────

def run_cluster(cluster: dict, args) -> dict:
    harness_config_path = pathlib.Path(args.harness_config)
    optimizable = yaml.safe_load(harness_config_path.read_text()).get("optimizable", [])
    kind, key = resolve_target(cluster, optimizable=optimizable if "::" in cluster["target_artifact"] else None)

    skill_name = (key if kind == "skill"
                  else _skill_for_domain(cluster["domain"], pathlib.Path(args.skills_root)))
    skill_path = pathlib.Path(args.skills_root) / skill_name

    spec = TargetSpec(kind=kind, key=key, skill_path=skill_path,
                      domain=cluster["domain"], tasks_dir=pathlib.Path(args.tasks_dir),
                      harness_config_path=harness_config_path)

    run_tag = f"{cluster['domain']}_{kind}_{key.replace('.', '-')}_{datetime.date.today().isoformat()}"
    out_root = OUTPUT_ROOT / run_tag

    adapter = TravelEnvAdapter(spec=spec, mock_mcp_url=args.mock_mcp_url,
                               split_seed=args.seed, seed=args.seed)
    baseline_text = initial_artifact(spec)

    from skillopt.config import load_config, flatten_config
    cfg = flatten_config(load_config(args.config))
    cfg["out_root"] = str(out_root)
    cfg["seed"] = args.seed
    # skill_init MUST be a file path — a text literal is silently treated as a
    # nonexistent path and the skill starts blank (spike findings §1)
    out_root.mkdir(parents=True, exist_ok=True)
    skill_init_path = out_root / "initial_artifact.md"
    skill_init_path.write_text(baseline_text)
    cfg["skill_init"] = str(skill_init_path)

    n_items = len(adapter.dataloader.load_raw_items(str(spec.tasks_dir)))
    n_train, n_sel, n_test = _split_counts(n_items)
    est_calls = estimate_rollout_calls(n_train, n_sel, n_test, cfg.get("num_epochs", 5))
    print(f"[{run_tag}] target={kind}:{key} tasks={n_items} (split {n_train}/{n_sel}/{n_test}) "
          f"~{est_calls} rollout calls (gpt-4o-mini)")

    if args.dry_run:
        return {"run": run_tag, "dry_run": True, "estimated_rollout_calls": est_calls}

    from eval.optimizer.skillopt_prompts import install_prompts
    install_prompts()   # 0.1.0 wheel ships no prompt files (findings §6)

    from skillopt.engine.trainer import ReflACTTrainer
    train_result = ReflACTTrainer(cfg, adapter).train()

    # Best artifact: out_root/best_skill.md, overwritten at each accept (findings §3)
    best_skill_file = out_root / "best_skill.md"
    best_text = best_skill_file.read_text() if best_skill_file.exists() else baseline_text

    # Held-out test: the trainer runs it itself when eval_test=true (findings §4),
    # scoring BOTH skill_init (baseline) and best_skill on the test split.
    # train() returns hard+soft for each; compute the mixed score ourselves.
    w = cfg.get("gate_mixed_weight", 0.5)
    base_score = _mixed_from(train_result.get("baseline_test_hard"),
                             train_result.get("baseline_test_soft"), w)
    best_score = _mixed_from(train_result.get("test_hard"),
                             train_result.get("test_soft"), w)

    report = {
        "run": run_tag, "target": f"{kind}:{key}", "cluster": cluster,
        "baseline_test_mixed": base_score, "best_test_mixed": best_score,
        "improved": best_score > base_score,
        "estimated_rollout_calls": est_calls,
        "train_result": _jsonable(train_result),
        "review_checklist": [
            "Read the proposed diff against the current artifact",
            "Run ab_compare on a SECOND skill before merging a harness change",
            "Verify the test-split tasks were never used for edit selection",
        ],
    }
    if report["improved"]:
        proposed = write_proposed(kind=kind, key=key, artifact_text=best_text,
                                  out_dir=out_root, harness_config_path=harness_config_path,
                                  skill_path=skill_path)
        report["proposed_file"] = str(proposed)
        print(f"[{run_tag}] IMPROVED on held-out test "
              f"({base_score:.2f} → {best_score:.2f}) — proposal: {proposed}")
    else:
        print(f"[{run_tag}] no candidate beat baseline on held-out test "
              f"({base_score:.2f} → {best_score:.2f}) — no proposal written")

    (out_root / "optimization_report.json").write_text(json.dumps(report, indent=2))
    return report


def _mixed_from(hard, soft, w: float = 0.5) -> float:
    """Mixed gate score from the trainer's returned hard/soft test scores."""
    if hard is None or soft is None:
        return 0.0
    return (1 - w) * float(hard) + w * float(soft)


def _split_counts(n: int, ratio=(5, 3, 2)) -> tuple[int, int, int]:
    total = sum(ratio)
    train = round(n * ratio[0] / total)
    sel = round(n * ratio[1] / total)
    return train, sel, n - train - sel


def _skill_for_domain(domain: str, skills_root: pathlib.Path) -> str:
    """Map a task domain to its skill dir (mirrors propose_skill._KNOWN_SKILLS)."""
    from eval.optimizer.propose_skill import _DOMAIN_TO_SKILL_NAME
    return _DOMAIN_TO_SKILL_NAME.get(domain, domain.replace("_", "-"))


def _jsonable(obj):
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Two-target skill/harness optimizer (propose-only).")
    parser.add_argument("--classification", default="failure_classification.json")
    parser.add_argument("--cluster", type=int, default=None, help="index into clusters; default all qualifying")
    parser.add_argument("--config", default="eval/optimizer/skillopt_config.yaml")
    parser.add_argument("--tasks-dir", default=str(DEFAULT_TASKS_DIR))
    parser.add_argument("--harness-config", default=str(DEFAULT_HARNESS_CONFIG))
    parser.add_argument("--skills-root", default=str(DEFAULT_SKILLS_ROOT))
    parser.add_argument("--mock-mcp-url", default="http://localhost:8000")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = json.loads(pathlib.Path(args.classification).read_text())
    clusters = data.get("clusters", [])
    targets = ([clusters[args.cluster]] if args.cluster is not None
               else qualifying_clusters(clusters))
    if not targets:
        print("No qualifying clusters.")
        return

    if not args.dry_run:
        preflight(args.mock_mcp_url)

    for cluster in targets:
        run_cluster(cluster, args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify against spike findings**

The code above is already reconciled with `docs/superpowers/specs/skillopt-spike-findings.md` (§1 skill_init file path, §3 best_skill.md, §4 eval_test=true, §6 install_prompts). Read the findings doc anyway and confirm nothing else applies — findings §8 lists surprises (steps_per_epoch ignored, use_gate mandatory, 3-rollouts-per-step shape).

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_optimize_driver.py -v`
Expected: 7 PASS

- [ ] **Step 6: Dry-run against the real classification**

Run: `.venv/bin/python -m eval.optimizer.optimize --classification failure_classification.json --dry-run`
Expected output: two clusters resolved (`harness:base_system_prompt` from 002/006, `harness:node_prompts` from 003), per-cluster task counts and call estimates printed, no API calls, exit 0.

- [ ] **Step 7: Commit**

```bash
git add eval/optimizer/optimize.py tests/test_optimize_driver.py
git commit -m "feat: add two-target optimization driver with dry-run and honest reporting"
```

---

### Task 8: Live smoke run (manual gate — costs ~$0.10–0.30, needs mock MCP + OPENAI_API_KEY)

**Files:** none modified — verification only. Outputs land under `eval/optimizer_output/` (gitignored or committed per outcome — see Step 4).

- [ ] **Step 1: Preflight**

```bash
lsof -i :8000 || (.venv/bin/python eval/mock_mcp/server.py & sleep 2)
.venv/bin/python -m eval.optimizer.optimize --dry-run
```

Confirm the printed estimate is sane (~50–90 rollout calls for the base_prompt cluster with 10 ancillery tasks).

- [ ] **Step 2: Run the harness:base_system_prompt cluster only**

```bash
.venv/bin/python -m eval.optimizer.optimize --cluster 0 2>&1 | tee /tmp/optimize_run.txt
```

(Confirm cluster 0 is the base_prompt cluster from the dry-run output; otherwise pass the right index.)

- [ ] **Step 3: Assess honestly**

- Did the trainer accept any edits? (check `optimization_report.json` + out_root history)
- Held-out test: baseline vs best mixed score — improvement, regression, or wash?
- Read the proposed `harness_config_proposed.yaml` diff vs `agent/harness_config.yaml` — is the edit sane (e.g. adds "you MUST call the tool" style instruction) or degenerate (deleted content, prompt-injection-ish text)?
- ALL outcomes are reportable, including "no candidate beat baseline — no proposal written". Do NOT tweak gates/configs to force a proposal.

- [ ] **Step 4: Record the outcome**

If a proposal was written: commit the report + proposal as evidence (they live under `eval/optimizer_output/`, never touch the real config):

```bash
git add eval/optimizer_output/
git commit -m "chore: record first optimizer smoke run on ancillery harness cluster"
```

If no proposal: commit just the report the same way. Either way, kill the mock server if you started it.

---

## Self-review notes

- **Spec coverage:** TargetSpec/materialization (Task 3) ← spec "two targets, concretely"; TravelTaskLoader (Task 4) ← "Adapter details"; rollout/reflect (Task 5) ← adapter contract incl. with_skill condition + env-var try/finally (safety rail 4); config (Task 6) ← spec config section incl. flatten-map verification; driver (Task 7) ← CLI, whitelist (rail 2), preflight, dry-run, honest no-improvement exit, report w/ review checklist (risk table); propose-only outputs (rail 1) ← `write_proposed` tests assert sources untouched; test-split-once (rail 3) ← driver runs it after train only. HARNESS_CONFIG_PATH override ← Task 1. skillopt dep ← Task 1. Spike + fallback posture (risk table) ← Task 2 with explicit BLOCKED instruction.
- **Known dependency chain:** Tasks 5/7 contain three integration points that consume Task 2's findings doc — flagged inline, not placeholders: the default code is runnable and the findings adjust it.
- **Type consistency check:** `TargetSpec(kind, key, skill_path, domain, tasks_dir, harness_config_path)` used identically in Tasks 3/5/7; `materialize_candidate(spec, artifact_text, out_dir) -> CandidateContext(skill_path, harness_config_path)` consistent; `resolve_target -> (kind, key)` consistent.
