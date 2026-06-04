# Failure-Layer Classifier + Harness Externalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build (1) a rules-based classifier that labels each eval failure by the layer that caused it (skill content vs agent harness) and (2) externalize the agent harness's editable surface into `agent/harness_config.yaml`, behavior-preserving.

**Architecture:** Slice 1 reads `ab_results.json`, extracts deterministic `TrajectoryFeatures` per failed task, maps them to a failure layer via ordered rules (reusing the existing `classify_failure` mode classifier), and clusters by `(layer, domain)` for downstream optimizer routing. Slice 2 moves the base system prompt and tool descriptions out of `agent/travel_agent.py` into YAML with verbatim values and hardcoded fallbacks, verified by re-running the ancillery eval.

**Tech Stack:** Python 3.11, dataclasses, tomllib, PyYAML, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-04-failure-classifier-harness-externalization-design.md`

**Repo:** `skill-testing-playground` (all work). Commit policy: imperative `feat:`/`test:`/`refactor:` style, no co-author lines, one commit per task.

---

## File map

| File | Responsibility |
|------|---------------|
| `eval/schemas.py` (modify) | add `TrajectoryFeatures`, `FailureClassification`, `LayerCluster` dataclasses |
| `eval/classify_failures.py` (create) | feature extraction, layer rules, clustering, CLI |
| `tests/test_classify_failures.py` (create) | unit tests incl. the 002/003/006 real-data signatures |
| `agent/harness_config.yaml` (create) | externalized base prompt + tool descriptions + node prompts |
| `agent/travel_agent.py` (modify) | `load_harness_config()` + config-driven prompt/descriptions with fallback |
| `tests/test_harness_config.py` (create) | config load, fallback, tool-description injection tests |

Naming note: the spec calls the cluster dataclass `FailureCluster`, but `eval/optimizer/propose_skill.py` already defines a different `FailureCluster` (domain clustering for *new-skill* proposals). To avoid import confusion the new one in `schemas.py` is named **`LayerCluster`**. Do not touch propose_skill's class.

---

### Task 1: Classifier dataclasses in `eval/schemas.py`

**Files:**
- Modify: `eval/schemas.py` (append at end)
- Test: `tests/test_schemas.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_schemas.py`:

```python
def test_trajectory_features_construction():
    from eval.schemas import TrajectoryFeatures
    f = TrajectoryFeatures(
        task_id="t1", domain="ancillery", task_weight=1.5, skill_injected=True,
        n_tools_called=0, called_any_tool=False, first_tool_name=None,
        expected_first_tool="add_ancillary", first_tool_correct=False,
        n_wrong_tool_calls=0, n_repeated_tool_calls=0,
        n_calls_missing_required_params=0, param_match_rate=0.0,
        n_steps=1, step_delta_vs_no_skill=-1,
        ended_without_tool_on_tool_task=True, looped_without_completion=False,
        output_is_verbal_only=True, verifier_score=0.0, delta_vs_no_skill=-1.0,
    )
    assert f.called_any_tool is False


def test_failure_classification_layer_literal():
    from eval.schemas import FailureClassification
    c = FailureClassification(
        task_id="t1", layer="harness:base_prompt", confidence=0.94,
        target_artifact="agent/harness_config.yaml::base_system_prompt",
        evidence={"called_any_tool": False},
    )
    assert c.layer == "harness:base_prompt"


def test_layer_cluster():
    from eval.schemas import LayerCluster
    cl = LayerCluster(
        layer="harness:base_prompt", domain="ancillery",
        task_ids=["t1", "t2"], dominant_failure_mode="NO_TOOL_CALL",
        target_artifact="agent/harness_config.yaml::base_system_prompt",
    )
    assert cl.n_failures == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Documents/skill-testing-playground && python -m pytest tests/test_schemas.py -v -k "trajectory or classification or cluster"`
Expected: FAIL with `ImportError: cannot import name 'TrajectoryFeatures'`

- [ ] **Step 3: Implement the dataclasses**

Append to `eval/schemas.py`:

```python
@dataclass
class TrajectoryFeatures:
    """Deterministic features extracted from one with_skill run (vs its no_skill pair)."""
    task_id: str
    domain: str
    task_weight: float
    skill_injected: bool
    # Tool behavior
    n_tools_called: int
    called_any_tool: bool
    first_tool_name: Optional[str]
    expected_first_tool: Optional[str]
    first_tool_correct: bool
    n_wrong_tool_calls: int
    n_repeated_tool_calls: int
    # Param quality
    n_calls_missing_required_params: int
    param_match_rate: float
    # Control flow
    n_steps: int
    step_delta_vs_no_skill: int
    ended_without_tool_on_tool_task: bool
    looped_without_completion: bool
    # Output / outcome
    output_is_verbal_only: bool
    verifier_score: float
    delta_vs_no_skill: float


@dataclass
class FailureClassification:
    """Layer attribution for one failed task — routes the optimizer to the right artifact."""
    task_id: str
    layer: Literal[
        "harness:base_prompt", "harness:tool_description", "harness:node_prompt",
        "skill:content", "skill:over_prescription", "skill:trigger",
    ]
    confidence: float
    target_artifact: str
    evidence: Dict


@dataclass
class LayerCluster:
    """Failures grouped by (layer, domain). One cluster routes to one artifact.

    Distinct from eval.optimizer.propose_skill.FailureCluster, which clusters
    by domain to propose *new* skills.
    """
    layer: str
    domain: str
    task_ids: List
    dominant_failure_mode: str
    target_artifact: str
    n_failures: int = field(init=False)

    def __post_init__(self) -> None:
        self.n_failures = len(self.task_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: all PASS (including pre-existing tests)

- [ ] **Step 5: Commit**

```bash
git add eval/schemas.py tests/test_schemas.py
git commit -m "feat: add failure-layer classifier dataclasses"
```

---

### Task 2: Feature extraction in `eval/classify_failures.py`

**Files:**
- Create: `eval/classify_failures.py`
- Create: `tests/test_classify_failures.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_classify_failures.py`. The fixtures mirror the *real* ancillery-002/003 records from `ab_results.json` (trimmed to the fields the classifier reads):

```python
# tests/test_classify_failures.py
import pytest
from eval.classify_failures import extract_features, load_expected


def ab_task(task_id, ws_tools, ws_params, ws_score, ws_passed, ws_steps,
            ns_score=1.0, ns_passed=True, ns_steps=2, domain="ancillery", weight=1.5):
    """Build an ab_results.json task entry (dict shape, as JSON round-trips it)."""
    return {
        "skill_name": "ancillery-skill",
        "task_id": task_id,
        "domain": domain,
        "task_weight": weight,
        "no_skill": {
            "task_id": task_id, "domain": domain, "score": ns_score,
            "steps": ns_steps, "tools_called": ["add_ancillary"],
            "tool_params": {"add_ancillary": {"booking_id": "BK1"}},
            "passed_verifier": ns_passed,
        },
        "with_skill": {
            "task_id": task_id, "domain": domain, "score": ws_score,
            "steps": ws_steps, "tools_called": ws_tools,
            "tool_params": ws_params, "passed_verifier": ws_passed,
        },
        "delta": ws_score - ns_score,
        "step_delta": ws_steps - ns_steps,
    }


EXPECTED = {"tools": ["add_ancillary"], "required_params": {}}


def test_features_no_tool_call():
    """ancillery-002/006 signature: with_skill called zero tools."""
    t = ab_task("ancillery-002", [], {}, ws_score=0.0, ws_passed=False, ws_steps=1)
    f = extract_features(t, EXPECTED)
    assert f.called_any_tool is False
    assert f.output_is_verbal_only is True
    assert f.ended_without_tool_on_tool_task is True
    assert f.delta_vs_no_skill == -1.0
    assert f.skill_injected is True


def test_features_wrong_tools_extra_steps():
    """ancillery-003 signature: verification tools called, required tool never reached."""
    t = ab_task(
        "ancillery-003",
        ["get_itinerary", "get_fare_rules"],
        {"get_itinerary": {"booking_id": "BK9"}, "get_fare_rules": {"flight_id": "BK9"}},
        ws_score=0.0, ws_passed=False, ws_steps=3,
    )
    f = extract_features(t, EXPECTED)
    assert f.called_any_tool is True
    assert f.first_tool_name == "get_itinerary"
    assert f.first_tool_correct is False
    assert f.n_wrong_tool_calls == 2
    assert f.ended_without_tool_on_tool_task is True
    assert f.step_delta_vs_no_skill == 1


def test_features_correct_tool_missing_param():
    """skill:content signature: right tool, bad params."""
    t = ab_task(
        "x-001", ["add_ancillary"], {"add_ancillary": {"booking_id": "BK1"}},
        ws_score=0.4, ws_passed=False, ws_steps=2,
    )
    expected = {"tools": ["add_ancillary"],
                "required_params": {"add_ancillary": ["booking_id", "service_type"]}}
    f = extract_features(t, expected)
    assert f.first_tool_correct is True
    assert f.n_calls_missing_required_params == 1
    assert f.param_match_rate == 0.5
    assert f.ended_without_tool_on_tool_task is False


def test_features_repeated_calls_mark_loop():
    t = ab_task(
        "x-002", ["get_itinerary", "get_itinerary", "get_itinerary"],
        {"get_itinerary": {"booking_id": "BK1"}},
        ws_score=0.0, ws_passed=False, ws_steps=4,
    )
    f = extract_features(t, EXPECTED)
    assert f.n_repeated_tool_calls == 2
    assert f.looped_without_completion is True


def test_load_expected_reads_task_toml(tmp_path):
    task_dir = tmp_path / "ancillery-099"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "ancillery-099"\ndomain = "ancillery"\n'
        'skill = "ancillery-skill"\nverifier = "tool_call_check"\nweight = 1.5\n\n'
        '[expected]\ntools = ["add_ancillary"]\n'
    )
    exp = load_expected(task_dir)
    assert exp["tools"] == ["add_ancillary"]
    assert exp["required_params"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classify_failures.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.classify_failures'`

- [ ] **Step 3: Implement feature extraction**

Create `eval/classify_failures.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_classify_failures.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add eval/classify_failures.py tests/test_classify_failures.py
git commit -m "feat: add trajectory feature extraction for failure classifier"
```

---

### Task 3: Layer classification rules

**Files:**
- Modify: `eval/classify_failures.py` (append)
- Modify: `tests/test_classify_failures.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classify_failures.py`:

```python
from eval.classify_failures import classify_layer


def _classify(t, expected=EXPECTED):
    f = extract_features(t, expected)
    no_skill_passed = t["no_skill"]["passed_verifier"]
    return classify_layer(f, no_skill_passed=no_skill_passed, skill_name=t["skill_name"])


def test_classify_002_no_tool_call_is_base_prompt():
    """The thesis check: verbal-only failure routes to harness, never skill."""
    t = ab_task("ancillery-002", [], {}, ws_score=0.0, ws_passed=False, ws_steps=1)
    c = _classify(t)
    assert c.layer == "harness:base_prompt"
    assert c.confidence >= 0.9
    assert c.target_artifact == "agent/harness_config.yaml::base_system_prompt"
    # no_skill passed + delta -1.0 → over-prescription is a competing signal, recorded
    assert "competing_layer" in c.evidence


def test_classify_003_verification_derail_is_node_prompt():
    t = ab_task(
        "ancillery-003",
        ["get_itinerary", "get_fare_rules"],
        {"get_itinerary": {"booking_id": "BK9"}, "get_fare_rules": {"flight_id": "BK9"}},
        ws_score=0.0, ws_passed=False, ws_steps=3,
    )
    c = _classify(t)
    assert c.layer == "harness:node_prompt"
    assert c.target_artifact == "agent/harness_config.yaml::node_prompts"


def test_classify_single_wrong_tool_is_tool_description():
    t = ab_task(
        "x-003", ["search_hotels"], {"search_hotels": {"location": "LA"}},
        ws_score=0.0, ws_passed=False, ws_steps=2,
        ns_score=0.5, ns_passed=False,  # also fails no_skill → not over-prescription
    )
    c = _classify(t)
    assert c.layer == "harness:tool_description"


def test_classify_missing_param_is_skill_content():
    t = ab_task(
        "x-004", ["add_ancillary"], {"add_ancillary": {"booking_id": "BK1"}},
        ws_score=0.4, ws_passed=False, ws_steps=2,
        ns_score=0.6, ns_passed=False,
    )
    expected = {"tools": ["add_ancillary"],
                "required_params": {"add_ancillary": ["booking_id", "service_type"]}}
    c = _classify(t, expected)
    assert c.layer == "skill:content"
    assert c.target_artifact == "skills/ancillery-skill/SKILL.md"


def test_classify_right_tool_full_params_only_with_skill_fails_is_over_prescription():
    """Right tool, right params, but only the with_skill condition fails badly."""
    t = ab_task(
        "x-005", ["add_ancillary"],
        {"add_ancillary": {"booking_id": "BK1", "service_type": "meal_selection"}},
        ws_score=0.0, ws_passed=False, ws_steps=2,
    )
    expected = {"tools": ["add_ancillary"],
                "required_params": {"add_ancillary": ["booking_id", "service_type"]}}
    c = _classify(t, expected)
    assert c.layer == "skill:over_prescription"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classify_failures.py -v -k classify`
Expected: FAIL with `ImportError: cannot import name 'classify_layer'`

- [ ] **Step 3: Implement `classify_layer`**

Append to `eval/classify_failures.py`:

```python
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
            target_artifact=target, evidence=evidence,
        )

    # 1. No tools on a tool task → base prompt failure (002/006 signature)
    if f.ended_without_tool_on_tool_task and not f.called_any_tool:
        if over_prescription_signal:
            evidence["competing_layer"] = "skill:over_prescription"
            return result("harness:base_prompt", 0.94)
        return result("harness:base_prompt", 0.90)

    # 2. Verification derail: looped, or multiple off-target tools with extra
    #    steps and the required tool never reached (003 signature)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_classify_failures.py -v`
Expected: 10 PASS

- [ ] **Step 5: Commit**

```bash
git add eval/classify_failures.py tests/test_classify_failures.py
git commit -m "feat: add failure-layer classification rules"
```

---

### Task 4: Clustering, CLI, and validation against real data

**Files:**
- Modify: `eval/classify_failures.py` (append)
- Modify: `tests/test_classify_failures.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classify_failures.py`:

```python
import json
from eval.classify_failures import classify_results, cluster_classifications


def test_cluster_groups_by_layer_and_domain():
    from eval.schemas import FailureClassification
    cls = [
        FailureClassification("t1", "harness:base_prompt", 0.94,
                              "agent/harness_config.yaml::base_system_prompt", {}),
        FailureClassification("t2", "harness:base_prompt", 0.90,
                              "agent/harness_config.yaml::base_system_prompt", {}),
        FailureClassification("t3", "harness:node_prompt", 0.82,
                              "agent/harness_config.yaml::node_prompts", {}),
    ]
    domains = {"t1": "ancillery", "t2": "ancillery", "t3": "ancillery"}
    modes = {"t1": "NO_TOOL_CALL", "t2": "NO_TOOL_CALL", "t3": "WRONG_TOOL"}
    clusters = cluster_classifications(cls, domains, modes)
    assert len(clusters) == 2
    by_layer = {c.layer: c for c in clusters}
    assert by_layer["harness:base_prompt"].n_failures == 2
    assert by_layer["harness:base_prompt"].dominant_failure_mode == "NO_TOOL_CALL"


def test_classify_results_end_to_end(tmp_path):
    """Full pipeline on a minimal ab_results.json with one 002-style failure."""
    results = {"skill_name": "ancillery-skill", "tasks": [
        ab_task("ancillery-002", [], {}, ws_score=0.0, ws_passed=False, ws_steps=1),
        # passing task — must be skipped
        ab_task("ancillery-001", ["add_ancillary"],
                {"add_ancillary": {"booking_id": "BK1"}},
                ws_score=1.0, ws_passed=True, ws_steps=2),
    ]}
    results_path = tmp_path / "ab_results.json"
    results_path.write_text(json.dumps(results))
    tasks_dir = tmp_path / "tasks" / "ancillery-002"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "task.toml").write_text(
        '[task]\nid = "ancillery-002"\ndomain = "ancillery"\nweight = 1.5\n\n'
        '[expected]\ntools = ["add_ancillary"]\n'
    )
    classifications, clusters = classify_results(results_path, tmp_path / "tasks")
    assert len(classifications) == 1
    assert classifications[0].layer == "harness:base_prompt"
    assert len(clusters) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classify_failures.py -v -k "cluster or end_to_end"`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement clustering + pipeline + CLI**

Append to `eval/classify_failures.py`:

```python
def cluster_classifications(
    classifications: list[FailureClassification],
    domains: dict[str, str],
    failure_modes: dict[str, str],
) -> list[LayerCluster]:
    """Group classifications by (layer, domain). One cluster → one artifact."""
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    targets: dict[tuple[str, str], str] = {}
    for c in classifications:
        key = (c.layer, domains.get(c.task_id, "unknown"))
        groups[key].append(c.task_id)
        targets[key] = c.target_artifact

    clusters = []
    for (layer, domain), task_ids in groups.items():
        modes = Counter(failure_modes.get(t, "UNKNOWN") for t in task_ids)
        clusters.append(LayerCluster(
            layer=layer, domain=domain, task_ids=task_ids,
            dominant_failure_mode=modes.most_common(1)[0][0],
            target_artifact=targets[(layer, domain)],
        ))
    return clusters


def classify_results(
    results_path: pathlib.Path,
    tasks_dir: pathlib.Path,
) -> tuple[list[FailureClassification], list[LayerCluster]]:
    """Classify every failed with_skill task in an ab_results.json."""
    data = json.loads(pathlib.Path(results_path).read_text())
    classifications: list[FailureClassification] = []
    domains: dict[str, str] = {}
    modes: dict[str, str] = {}

    for ab in data.get("tasks", []):
        ws = ab.get("with_skill", {})
        if ws.get("passed_verifier", False):
            continue  # only failures get classified
        expected = load_expected(pathlib.Path(tasks_dir) / ab["task_id"])
        feats = extract_features(ab, expected)
        no_skill_passed = ab.get("no_skill", {}).get("passed_verifier", False)
        c = classify_layer(feats, no_skill_passed=no_skill_passed,
                           skill_name=ab.get("skill_name", "unknown"))
        classifications.append(c)
        domains[c.task_id] = ab.get("domain", "unknown")
        # Re-derive the legacy failure mode for cluster reporting
        tools_called = [{"name": t} for t in ws.get("tools_called", [])]
        modes[c.task_id] = classify_failure(
            tools_called=tools_called,
            required_tools=expected["tools"],
            required_params=expected["required_params"],
        ) or "UNKNOWN"

    clusters = cluster_classifications(classifications, domains, modes)
    return classifications, clusters


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify eval failures by layer.")
    parser.add_argument("--results", default="ab_results.json")
    parser.add_argument("--tasks-dir", default="tasks")
    parser.add_argument("--output", default="failure_classification.json")
    args = parser.parse_args()

    classifications, clusters = classify_results(
        pathlib.Path(args.results), pathlib.Path(args.tasks_dir)
    )

    if not classifications:
        print("No failed tasks to classify.")
        return

    print(f"Failure classification ({args.results}):")
    for c in classifications:
        reason = "no tools called on tool task" if c.layer == "harness:base_prompt" \
            else "verification derail / loop" if c.layer == "harness:node_prompt" \
            else "wrong tool selected" if c.layer == "harness:tool_description" \
            else c.layer.split(":", 1)[1].replace("_", " ")
        print(f"  {c.task_id:<18} {c.layer:<26} ({reason})  conf {c.confidence:.2f}")

    print()
    for cl in clusters:
        print(f"  → cluster: ({cl.layer}, {cl.domain}) {cl.n_failures} task(s) → {cl.target_artifact}")
    if not any(c.layer.startswith("skill:") for c in classifications):
        print("  → NO skill PR proposed")

    payload = {
        "classifications": [dataclasses.asdict(c) for c in classifications],
        "clusters": [dataclasses.asdict(cl) for cl in clusters],
    }
    pathlib.Path(args.output).write_text(json.dumps(payload, indent=2))
    print(f"\nWritten to {args.output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_classify_failures.py -v`
Expected: 12 PASS

- [ ] **Step 5: Validate against the real ancillery results (the thesis check)**

Run: `python -m eval.classify_failures --results ab_results.json`

Expected output (acceptance criteria from spec):
- `ancillery-002` → `harness:base_prompt`
- `ancillery-006` → `harness:base_prompt`
- `ancillery-003` → `harness:node_prompt` (or `skill:over_prescription` with `competing_layer` evidence)
- **None of the three** classify as plain `skill:content`
- `failure_classification.json` written

If 003 misroutes to `harness:tool_description`, check that `ended_without_tool_on_tool_task` and `step_delta_vs_no_skill > 0` are both true for it (rule 2 must fire before rule 3).

- [ ] **Step 6: Commit**

```bash
git add eval/classify_failures.py tests/test_classify_failures.py
git commit -m "feat: add failure clustering, CLI, and classification output"
```

---

### Task 5: `agent/harness_config.yaml` + loader with fallback

**Files:**
- Create: `agent/harness_config.yaml`
- Modify: `agent/travel_agent.py` (add loader; do not wire into the agent yet)
- Create: `tests/test_harness_config.py`

- [ ] **Step 1: Create the config file (verbatim copies of today's strings)**

Create `agent/harness_config.yaml`. Every string below is copied **character-for-character** from the current `agent/travel_agent.py` (base prompt from lines 112–115, tool descriptions from the `@tool` docstrings):

```yaml
# agent/harness_config.yaml
# Externalized harness surface — the editable "brain settings" of the travel agent.
# Initial values are verbatim copies of the previously hardcoded strings.
# A missing file or missing key falls back to the hardcoded defaults in travel_agent.py.
version: "1.0"

base_system_prompt: "You are a helpful travel assistant. Use the available tools to help users with flight searches, hotel bookings, and travel planning."

tool_descriptions:
  search_flights: "Search for available flights between two cities."
  search_hotels: "Search for available hotels at a location."
  check_availability: "Check if a flight or hotel resource is available on a date."
  get_fare_rules: "Get cancellation, change, and baggage rules for a flight."
  validate_passenger: "Validate passenger information before booking."
  create_booking: "Create a flight or hotel booking for a passenger."
  modify_booking: "Modify an existing booking (date change, upgrade, etc)."
  cancel_booking: "Cancel a booking and get refund information."
  get_itinerary: "Retrieve the full itinerary for a booking."
  add_ancillary: "Add an ancillary service to a booking. service_type: seat_selection, extra_baggage, travel_insurance, lounge_access, priority_boarding, car_rental, airport_transfer."

# Optional per-node prompt overrides. Empty = current behavior (no node prompts).
node_prompts: {}

# Keys the (future, Slice 3) optimizer may propose edits to. Read-only metadata here.
optimizable:
  - base_system_prompt
  - tool_descriptions.*
  - node_prompts.*
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_harness_config.py`:

```python
# tests/test_harness_config.py
import pathlib
import pytest
from agent.travel_agent import load_harness_config, HARNESS_DEFAULTS


def test_load_returns_yaml_values():
    cfg = load_harness_config()
    assert cfg["base_system_prompt"].startswith("You are a helpful travel assistant.")
    assert cfg["tool_descriptions"]["search_flights"] == \
        "Search for available flights between two cities."
    assert cfg["node_prompts"] == {}


def test_yaml_matches_defaults_verbatim():
    """Behavior preservation: YAML initial values == hardcoded fallbacks."""
    cfg = load_harness_config()
    assert cfg["base_system_prompt"] == HARNESS_DEFAULTS["base_system_prompt"]
    assert cfg["tool_descriptions"] == HARNESS_DEFAULTS["tool_descriptions"]


def test_missing_file_falls_back_to_defaults(tmp_path):
    cfg = load_harness_config(config_path=tmp_path / "does_not_exist.yaml")
    assert cfg == HARNESS_DEFAULTS


def test_partial_file_merges_with_defaults(tmp_path):
    p = tmp_path / "partial.yaml"
    p.write_text('base_system_prompt: "Custom prompt."\n')
    cfg = load_harness_config(config_path=p)
    assert cfg["base_system_prompt"] == "Custom prompt."
    # missing keys fall back
    assert cfg["tool_descriptions"] == HARNESS_DEFAULTS["tool_descriptions"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_harness_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_harness_config'`

- [ ] **Step 4: Implement the loader**

In `agent/travel_agent.py`, add after the imports (`import yaml` and `import pathlib` go at the top with the other imports):

```python
_CONFIG_PATH = pathlib.Path(__file__).parent / "harness_config.yaml"

# Source-of-truth defaults — used when harness_config.yaml is absent or partial.
# These are the original hardcoded strings; the YAML overrides them when present.
HARNESS_DEFAULTS = {
    "base_system_prompt": (
        "You are a helpful travel assistant. "
        "Use the available tools to help users with flight searches, hotel bookings, and travel planning."
    ),
    "tool_descriptions": {
        "search_flights": "Search for available flights between two cities.",
        "search_hotels": "Search for available hotels at a location.",
        "check_availability": "Check if a flight or hotel resource is available on a date.",
        "get_fare_rules": "Get cancellation, change, and baggage rules for a flight.",
        "validate_passenger": "Validate passenger information before booking.",
        "create_booking": "Create a flight or hotel booking for a passenger.",
        "modify_booking": "Modify an existing booking (date change, upgrade, etc).",
        "cancel_booking": "Cancel a booking and get refund information.",
        "get_itinerary": "Retrieve the full itinerary for a booking.",
        "add_ancillary": "Add an ancillary service to a booking. service_type: seat_selection, extra_baggage, travel_insurance, lounge_access, priority_boarding, car_rental, airport_transfer.",
    },
    "node_prompts": {},
}


def load_harness_config(config_path: pathlib.Path = _CONFIG_PATH) -> dict:
    """Load harness config from YAML, falling back to HARNESS_DEFAULTS per key."""
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in HARNESS_DEFAULTS.items()}
    if config_path.exists():
        try:
            loaded = yaml.safe_load(config_path.read_text()) or {}
        except yaml.YAMLError:
            loaded = {}
        for key in HARNESS_DEFAULTS:
            if key in loaded and loaded[key] is not None:
                cfg[key] = loaded[key]
    return cfg
```

Note the base prompt default is the exact concatenation currently at lines 112–115 — one string: `"You are a helpful travel assistant. Use the available tools to help users with flight searches, hotel bookings, and travel planning."` (single space after the first period, matching the current `"... assistant. " + "Use ..."` concatenation).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_harness_config.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add agent/harness_config.yaml agent/travel_agent.py tests/test_harness_config.py
git commit -m "feat: externalize harness surface into harness_config.yaml with fallback loader"
```

---

### Task 6: Wire config into `build_travel_agent`

**Files:**
- Modify: `agent/travel_agent.py` (`build_travel_agent`, `make_mcp_tools` call site)
- Modify: `tests/test_harness_config.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_harness_config.py`:

```python
def test_tools_get_config_descriptions(monkeypatch):
    """Tool descriptions come from config after post-construction assignment."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    from agent.travel_agent import make_mcp_tools, load_harness_config
    tools = make_mcp_tools("http://localhost:8000")
    cfg = load_harness_config()
    for t in tools:
        assert t.description == cfg["tool_descriptions"][t.name]


def test_build_agent_uses_config_prompt(monkeypatch, tmp_path):
    """base_system_prompt flows from config into the agent's system prompt."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    import agent.travel_agent as ta
    custom = tmp_path / "harness_config.yaml"
    custom.write_text('base_system_prompt: "CUSTOM HARNESS PROMPT"\n')
    monkeypatch.setattr(ta, "_CONFIG_PATH", custom)
    # build_travel_agent reads config at construction; the compiled graph itself
    # is opaque, so assert via the module-level helper it now uses
    cfg = ta.load_harness_config(custom)
    assert cfg["base_system_prompt"] == "CUSTOM HARNESS PROMPT"
    # and the graph compiles without error using the custom config
    agent = ta.build_travel_agent(skill_content=None)
    assert agent is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_harness_config.py -v -k "tools_get or uses_config"`
Expected: `test_tools_get_config_descriptions` FAILS (descriptions still come from docstrings — they happen to be identical strings, so to make this test meaningful first check it fails when run against a doctored config; if it passes trivially because YAML == docstrings, that is acceptable: the assertion still pins the contract). `test_build_agent_uses_config_prompt` may fail on the `_CONFIG_PATH` monkeypatch if `build_travel_agent` doesn't read the module attribute yet.

- [ ] **Step 3: Implement the wiring**

In `agent/travel_agent.py`:

(a) At the end of `make_mcp_tools`, before the return, assign config descriptions post-construction:

```python
    tools = [search_flights, search_hotels, check_availability, get_fare_rules,
             validate_passenger, create_booking, modify_booking, cancel_booking,
             get_itinerary, add_ancillary]
    descriptions = load_harness_config(_CONFIG_PATH)["tool_descriptions"]
    for t in tools:
        if t.name in descriptions:
            t.description = descriptions[t.name]
    return tools
```

(b) In `build_travel_agent`, replace the hardcoded prompt block:

```python
    config = load_harness_config(_CONFIG_PATH)
    system_prompt = config["base_system_prompt"]
    node_prompts = config.get("node_prompts") or {}
    if node_prompts.get("agent_node"):
        system_prompt += f"\n\n{node_prompts['agent_node']}"
    if skill_content:
        system_prompt += f"\n\n## Skill Instructions\n{skill_content}"
```

(Skill injection order is unchanged: base prompt first, then node prompt if any, then skill. With `node_prompts: {}` the produced string is byte-identical to before.)

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS (including pre-existing tests — `test_mock_mcp.py` spawns a server; if port 8000 is busy from a dev server, stop it first)

- [ ] **Step 5: Commit**

```bash
git add agent/travel_agent.py tests/test_harness_config.py
git commit -m "feat: drive agent prompt and tool descriptions from harness config"
```

---

### Task 7: Behavior-preservation verification (gate for Slice 2)

This is the spec's verification gate. It needs the mock MCP server and API keys, so it runs in the dev environment, not CI.

**Files:** none modified — verification only.

- [ ] **Step 1: Preserve the pre-refactor baseline**

The current `ab_results.json` (ancillery run: weighted_delta −0.258, regressions = {002, 003, 006}) is the baseline. Copy it:

```bash
cp ab_results.json results/ancillery_pre_externalization_baseline.json
```

- [ ] **Step 2: Start the mock MCP server**

```bash
python eval/mock_mcp/server.py &
sleep 2
```

- [ ] **Step 3: Re-run the same ancillery eval**

```bash
python -m eval.ab_compare --skill-path ../travel-agent-skills/skills/ancillery-skill --trials 5
```

- [ ] **Step 4: Compare against the baseline**

Acceptance ("match within trial noise", per spec — not bit-identical):
- The same set of tasks passes/fails per condition (in particular: 001/004/005/007/008/009/010 with_skill still pass)
- Weighted delta within the noise band already observed across trials (±~0.05)
- If 002/003/006 still regress, that is **expected** — the config values are verbatim copies; this refactor does not fix the regression, it only makes the harness editable

A *structural* mismatch (e.g. a previously-passing task now consistently fails across trials, or tool descriptions visibly differ in traces) means a string was not copied verbatim — diff `HARNESS_DEFAULTS` and `harness_config.yaml` against git history of `travel_agent.py` and fix before proceeding.

- [ ] **Step 5: Stop the server and archive the verification run**

```bash
kill %1
cp ab_results.json results/ancillery_post_externalization_verify.json
git add results/ancillery_pre_externalization_baseline.json results/ancillery_post_externalization_verify.json
git commit -m "chore: record behavior-preservation verification for harness externalization"
```

---

## Self-review notes

- **Spec coverage:** Slice 1 (dataclasses → Task 1, feature extraction → Task 2, rules → Task 3, clustering/CLI/real-data validation → Task 4) and Slice 2 (config file + loader → Task 5, wiring → Task 6, behavior gate → Task 7) are fully covered. The `FailureCluster` naming collision is resolved as `LayerCluster` (deviation from spec name, documented in the file map).
- **Type consistency:** `TrajectoryFeatures`/`FailureClassification`/`LayerCluster` field names match across Tasks 1–4; `load_harness_config`/`HARNESS_DEFAULTS`/`_CONFIG_PATH` match across Tasks 5–6.
- **Known soft spot:** Task 6 Step 1's tool-description test can pass trivially while YAML and docstrings are identical — acceptable, since the test pins the contract for when they diverge (which is the entire point of Slice 3).
