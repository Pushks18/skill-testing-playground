# Phase 8 Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embedding router + per-domain specialist agents (scoped tools, always-injected skill), opt-in via `agent_mode="orchestrated"`, with a bank-wide mono-vs-orchestrated comparison and a free router-accuracy report.

**Architecture:** `AgentRouter` (wraps the existing `eval.skill_router.SkillRouter`) lazily builds one specialist per skill via `build_specialist_agent` (which calls `build_travel_agent` with a new `tools_subset` param). `run_task` gains `agent_mode`; `eval/orchestrator_compare.py` measures both router accuracy and end-to-end quality deltas.

**Tech Stack:** existing — LangGraph agent, sentence-transformers router, pytest. No new deps.

**Spec:** `docs/superpowers/specs/2026-06-05-phase8-orchestrator-design.md` (read it first — SKILL_TOOLS map, affinity rule, eval design live there).

---

## Execution preamble

- Repo `/Users/pushkaraj/Documents/skill-testing-playground`; `.venv/bin/python`; commits imperative, NO co-author lines, one per task; `git add` only named files (repo has unrelated drift).
- Skills root for specialists: `../travel-agent-skills/skills` (9 evaluable skills + nested detection suite which the router must SKIP — no top-level SKILL.md).
- Existing contracts to reuse, not reinvent: `SkillRouter.from_skill_dir(path)`, `.route(text, threshold)→RouteMatch|None`; `eval/skill_loader.load_skill(dir)→LoadedSkill(.body)`; `build_travel_agent(skill_content=, mock_mcp_url=)`.

### Task map

| Task | Files |
|---|---|
| 1. `tools_subset` in build_travel_agent | agent/travel_agent.py, tests/test_harness_config.py (append) |
| 2. specialists module | agent/specialists.py, tests/test_specialists.py |
| 3. AgentRouter | agent/router.py, tests/test_router.py |
| 4. run_task agent_mode | eval/run_task.py, tests/test_multi_turn.py (append) |
| 5. orchestrator_compare | eval/orchestrator_compare.py, tests/test_orchestrator_compare.py |
| 6. live: router accuracy (free) + pilot + full bank | results/ |

---

### Task 1: `tools_subset` param

**Files:** Modify `agent/travel_agent.py`; Test: append `tests/test_harness_config.py`

- [ ] **Step 1: failing test** — append:

```python
def test_build_agent_tools_subset(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    from agent.travel_agent import make_mcp_tools
    tools = make_mcp_tools("http://localhost:8000", tools_subset=["search_flights", "get_fare_rules"])
    assert sorted(t.name for t in tools) == ["get_fare_rules", "search_flights"]


def test_build_agent_tools_subset_none_means_all(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    from agent.travel_agent import make_mcp_tools
    assert len(make_mcp_tools("http://localhost:8000", tools_subset=None)) == 10


def test_build_agent_tools_subset_unknown_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    from agent.travel_agent import make_mcp_tools
    with pytest.raises(ValueError, match="unknown tool"):
        make_mcp_tools("http://localhost:8000", tools_subset=["teleport"])
```

- [ ] **Step 2:** run `-k tools_subset` → FAIL (unexpected kwarg)
- [ ] **Step 3: implement** — `make_mcp_tools(base_url, tools_subset: list[str] | None = None)`: after building the full `tools` list and applying config descriptions, filter:

```python
    if tools_subset is not None:
        by_name = {t.name: t for t in tools}
        unknown = [n for n in tools_subset if n not in by_name]
        if unknown:
            raise ValueError(f"unknown tool(s) in subset: {unknown}")
        tools = [by_name[n] for n in tools_subset]
    return tools
```

`build_travel_agent(skill_content=None, mock_mcp_url=..., model=None, tools_subset=None)` threads it through to `make_mcp_tools`. Everything else untouched (`tool_map` derives from the filtered list — verify it does).

- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_harness_config.py -q` → all pass
- [ ] **Step 5:** commit `feat: add tools_subset filter to agent factory`

---

### Task 2: specialists module

**Files:** Create `agent/specialists.py`, `tests/test_specialists.py`

- [ ] **Step 1: failing tests**

```python
# tests/test_specialists.py
import pathlib
import pytest

from agent.specialists import SKILL_TOOLS, build_specialist_agent, specialist_config

SKILLS_ROOT = pathlib.Path("../travel-agent-skills/skills")


def test_skill_tools_reference_real_tools():
    from eval.taskgen import VALID_TOOLS
    for skill, tools in SKILL_TOOLS.items():
        assert set(tools) <= set(VALID_TOOLS), skill


def test_specialist_config_scoped():
    cfg = specialist_config("ancillery-skill", SKILLS_ROOT)
    assert cfg["tools_subset"] == SKILL_TOOLS["ancillery-skill"]
    assert "Ancillery" in cfg["skill_content"] or "ancillary" in cfg["skill_content"].lower()


def test_specialist_config_unlisted_skill_gets_all_tools():
    cfg = specialist_config("planning-skill", SKILLS_ROOT)
    assert cfg["tools_subset"] is None          # None = all 10


def test_specialist_config_missing_skill_raises():
    with pytest.raises(FileNotFoundError):
        specialist_config("no-such-skill", SKILLS_ROOT)


def test_build_specialist_agent_compiles(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    agent = build_specialist_agent("fare-rules", SKILLS_ROOT, mock_mcp_url="http://localhost:8000")
    assert agent is not None
```

- [ ] **Step 2:** run → ModuleNotFoundError
- [ ] **Step 3: implement** `agent/specialists.py`:

```python
# agent/specialists.py
"""Per-domain specialist agents: one skill always injected, tools scoped.

SKILL_TOOLS is deliberately conservative — unlisted skills (planning) get all
tools (tools_subset=None). The map is data; it can migrate into skill
frontmatter later.
"""
from __future__ import annotations

import pathlib

from agent.travel_agent import build_travel_agent
from eval.skill_loader import load_skill

SKILL_TOOLS: dict[str, list[str]] = {
    # (copy the exact map from the spec §Tool scoping)
}


def specialist_config(skill_name: str, skills_root: pathlib.Path) -> dict:
    """Resolve a specialist's skill body + tool subset. Raises if skill missing."""
    skill = load_skill(pathlib.Path(skills_root) / skill_name)
    if skill is None:
        raise FileNotFoundError(f"no SKILL.md for {skill_name!r} under {skills_root}")
    return {"skill_content": skill.body,
            "tools_subset": SKILL_TOOLS.get(skill_name)}


def build_specialist_agent(skill_name: str, skills_root: pathlib.Path,
                           mock_mcp_url: str = "http://localhost:8000"):
    cfg = specialist_config(skill_name, skills_root)
    return build_travel_agent(skill_content=cfg["skill_content"],
                              mock_mcp_url=mock_mcp_url,
                              tools_subset=cfg["tools_subset"])
```

(Fill SKILL_TOOLS verbatim from the spec.)

- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_specialists.py -q` → 5 pass
- [ ] **Step 5:** commit `feat: add specialist agent factory with scoped tools`

---

### Task 3: AgentRouter

**Files:** Create `agent/router.py`, `tests/test_router.py`

- [ ] **Step 1: failing tests**

```python
# tests/test_router.py
import pathlib
import pytest

from agent.router import AgentRouter

SKILLS_ROOT = pathlib.Path("../travel-agent-skills/skills")


@pytest.fixture(scope="module")
def router():
    return AgentRouter(SKILLS_ROOT, mock_mcp_url="http://localhost:8000")


def test_routes_obvious_domains(router):
    assert router.route_skill("Find me flights from JFK to LAX next Friday") == "flight-search"
    assert router.route_skill("I need a hotel in Paris for two nights") == "hotel-search"
    assert router.route_skill("My flight got cancelled, rebook me, ref BK1A2B3C") == "disruption-handling"


def test_low_confidence_falls_back_to_planning(router):
    assert router.route_skill("hmm") == "planning-skill"


def test_router_skips_nested_suite(router):
    # detection sub-suite has no top-level SKILL.md and must not be a route target
    assert "disruption-skill" not in router.available_skills()
    assert "flight-disruption-detection" not in router.available_skills()


def test_agent_cache_lazy_and_reused(router, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    a1 = router.agent_for("fare-rules")
    a2 = router.agent_for("fare-rules")
    assert a1 is a2
```

- [ ] **Step 2:** run → ModuleNotFoundError. NOTE: these tests load the MiniLM model (~5s first call) — acceptable; mark module with `@pytest.mark.slow`? NO — router accuracy matters too much; keep them fast-path (model is cached process-wide by SkillRouter).
- [ ] **Step 3: implement** `agent/router.py`:

```python
# agent/router.py
"""Phase 8 orchestrator: embedding router → per-domain specialist agents.

Route ONCE per conversation (multi-turn affinity is the caller's job: keep
using the returned agent). Below-threshold matches fall back to the planning
specialist, which keeps all tools.
"""
from __future__ import annotations

import pathlib

from eval.skill_router import SkillRouter
from agent.specialists import build_specialist_agent

FALLBACK_SKILL = "planning-skill"
ROUTE_THRESHOLD = 0.35


class AgentRouter:
    def __init__(self, skills_root: pathlib.Path,
                 mock_mcp_url: str = "http://localhost:8000",
                 threshold: float = ROUTE_THRESHOLD):
        self.skills_root = pathlib.Path(skills_root)
        self.mock_mcp_url = mock_mcp_url
        self.threshold = threshold
        self._router = SkillRouter.from_skill_dir(self.skills_root)
        self._agents: dict[str, object] = {}

    def available_skills(self) -> list[str]:
        return sorted(self._router._skills)      # SkillRouter's skill map

    def route_skill(self, text: str) -> str:
        match = self._router.route(text, threshold=self.threshold)
        return match.skill_name if match else FALLBACK_SKILL

    def agent_for(self, skill_name: str):
        if skill_name not in self._agents:
            self._agents[skill_name] = build_specialist_agent(
                skill_name, self.skills_root, self.mock_mcp_url)
        return self._agents[skill_name]

    def route(self, text: str):
        """(skill_name, agent) for a new conversation."""
        name = self.route_skill(text)
        return name, self.agent_for(name)
```

CHECK FIRST: does `SkillRouter.from_skill_dir` skip dirs without SKILL.md (the nested suite)? Read `eval/skill_router.py:51-65` — if it globs `*/SKILL.md` it skips naturally; if it would crash or include them, filter in AgentRouter init. Also confirm `_skills` attr name; if private access is fragile add an `available()` accessor to SkillRouter instead (1-line, allowed).

- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_router.py -q` → 4 pass. If `test_routes_obvious_domains` fails on a phrasing, adjust the phrasing ONLY if the score is borderline (<0.05 off); a real misroute on an obvious phrase = report, do not paper over.
- [ ] **Step 5:** commit `feat: add embedding agent router with specialist cache`

---

### Task 4: `agent_mode` in run_task

**Files:** Modify `eval/run_task.py`; Test: append `tests/test_multi_turn.py`

- [ ] **Step 1: failing test** — append:

```python
def test_run_task_orchestrated_routes(monkeypatch, tmp_path):
    """orchestrated mode: router picks the agent; skill_path/condition ignored."""
    import eval.run_task as rt

    class _FakeAgent:
        def invoke(self, state, config=None):
            return {"messages": [], "response": "done",
                    "tools_called": [{"name": "add_ancillary", "params": {}}],
                    "step_timings": [], "steps": 1,
                    "tokens_used": 10, "input_tokens": 8, "output_tokens": 2}

    class _FakeRouter:
        def route(self, text):
            return "ancillery-skill", _FakeAgent()

    monkeypatch.setattr(rt, "_get_agent_router", lambda url: _FakeRouter())

    task_dir = tmp_path / "anc-001"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "anc-001"\ndomain = "ancillery"\nskill = "ancillery-skill"\n'
        'verifier = "tool_call_check"\nweight = 1.5\n\n[expected]\ntools = ["add_ancillary"]\n')
    (task_dir / "instruction.md").write_text("Add a bag to booking BK1A2B3C")

    r = rt.run_task(str(task_dir), None, "no_skill", "http://unused", agent_mode="orchestrated")
    assert r.skill_name == "ancillery-skill"      # the ROUTED skill is recorded
    assert r.passed_verifier
```

- [ ] **Step 2:** run → TypeError (unexpected kwarg)
- [ ] **Step 3: implement** in `eval/run_task.py`:
  - module-level lazy singleton:

```python
_AGENT_ROUTER = None

def _get_agent_router(mock_mcp_url: str):
    global _AGENT_ROUTER
    if _AGENT_ROUTER is None:
        from agent.router import AgentRouter
        import pathlib as _pl
        _AGENT_ROUTER = AgentRouter(_pl.Path("../travel-agent-skills/skills"),
                                    mock_mcp_url=mock_mcp_url)
    return _AGENT_ROUTER
```

  - `run_task(..., agent_mode: str = "mono")`: when `"orchestrated"` — `routed_skill, agent = _get_agent_router(mock_mcp_url).route(task["instruction"])`; `skill_name = routed_skill`; skip `load_skill`/`build_travel_agent`; condition tag becomes `"orchestrated"` in the LangSmith tags + run_name (so traces distinguish). Multi-turn loop unchanged — SAME agent reused each round (affinity for free).
  - EvalResult: `skill_name=routed_skill`, everything else as-is.

- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_multi_turn.py -q` → all pass
- [ ] **Step 5:** commit `feat: add orchestrated agent mode to run_task`

---

### Task 5: orchestrator_compare

**Files:** Create `eval/orchestrator_compare.py`, `tests/test_orchestrator_compare.py`

- [ ] **Step 1: failing tests** — test the pure parts:

```python
# tests/test_orchestrator_compare.py
from eval.orchestrator_compare import router_accuracy, summarize_modes


def test_router_accuracy_counts():
    labels = [("find flights", "flight-search"), ("hotel in rome", "hotel-search"),
              ("hello", None)]
    routed = ["flight-search", "flight-search", "planning-skill"]
    rep = router_accuracy(labels, routed, fallback="planning-skill")
    fs = rep["per_skill"]["flight-search"]
    assert fs["tp"] == 1 and fs["fp"] == 1
    assert rep["per_skill"]["hotel-search"]["fn"] == 1
    assert rep["null_correct"] == 1            # 'hello' → fallback counts as correct null


def test_summarize_modes_weighted_delta():
    mono = [{"task_id": "t1", "domain": "ancillery", "score": 0.5},
            {"task_id": "t2", "domain": "ancillery", "score": 1.0}]
    orch = [{"task_id": "t1", "domain": "ancillery", "score": 1.0},
            {"task_id": "t2", "domain": "ancillery", "score": 1.0}]
    s = summarize_modes(mono, orch)
    assert s["per_domain"]["ancillery"]["delta"] == 0.25
    assert s["overall_delta"] > 0
```

- [ ] **Step 2:** run → ModuleNotFoundError
- [ ] **Step 3: implement** `eval/orchestrator_compare.py` with:
  - `router_accuracy(labels, routed, fallback)` — labels = [(text, expected_skill_or_None)]; per-skill tp/fp/fn + precision/recall, `null_correct` for None-labels routed to fallback.
  - `route_report(skills_root, labeled_path="trigger/labeled_requests.json", tasks_dir="tasks")` — loads the 60 labeled requests (READ the json format first; map its label field; label "null"/None → None; note: it uses "book-itinerary" as a label name — map legacy label names via propose_skill's `_DOMAIN_TO_SKILL_NAME` or a small alias dict) AND all task instructions labeled by their task.toml `skill` field; routes everything with `AgentRouter.route_skill`; prints + returns both accuracy tables. NO agent calls — embeddings only.
  - `run_bank(domains, trials, mode, mock_mcp_url)` — asyncio parallel like ab_compare (copy its executor pattern incl. EVAL_CONCURRENCY semaphore): for each task in the selected domains run `run_task(task_path, skill_path=<designated skill> if mode=="mono" else None, condition="with_skill" if mono else "orchestrated", agent_mode=mode)` × trials, best-of-N per task (consistent with ab_compare). For mono, designated skill dir = `../travel-agent-skills/skills/<task.toml skill>`. Record per task: best score, routed skill (orchestrated: from EvalResult.skill_name), misroute flag (routed != designated).
  - `summarize_modes(mono_results, orch_results)` — per-domain mean-score deltas using gate_check.TASK_WEIGHTS, overall weighted delta, misroute list.
  - CLI: `--accuracy-only` (free), `--domains a,b`, `--trials 3`, `--output results/orchestrator_compare.json`. Preflight mock MCP + OPENAI key for paid path (copy optimize.py's preflight).
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_orchestrator_compare.py -q` → green
- [ ] **Step 5:** commit `feat: add mono-vs-orchestrated comparison harness`

---

### Task 6: live runs (free → pilot → full)

**Files:** results/ only.

- [ ] **Step 1 (FREE): router accuracy** — `.venv/bin/python -m eval.orchestrator_compare --accuracy-only 2>&1 | tail -30`. Gate per PRD targets: P ≥ 0.85, R ≥ 0.80 overall. If router accuracy is BAD, STOP — report which phrasings misroute (the paid comparison would be measuring routing noise; skill descriptions may need editing, which is a human/optimizer decision).
- [ ] **Step 2 (pilot, ~$0.05):** `--domains ancillery,disruption --trials 3`. Sanity: orchestrated runs actually route (check misroute counts), scores sane.
- [ ] **Step 3 (full, ~$0.50, ONE run):** all domains, `--trials 3`. Honest report: per-domain deltas, overall weighted delta, misroutes, fallback counts.
- [ ] **Step 4:** commit results `chore: record mono-vs-orchestrated comparison`.

The decision (adopt orchestrated mode for evals/CI, iterate on scoping, or shelve) is the HUMAN's, made on this report.

---

## Self-review notes

- Spec coverage: tools_subset (T1), SKILL_TOOLS+specialists (T2), router+fallback+cache+nested-suite skip (T3), agent_mode+affinity+trace tags (T4), both eval questions incl. legacy label aliasing (T5), staged live rollout with free gate first (T6). Out-of-scope items untouched.
- Type consistency: `specialist_config -> dict(skill_content, tools_subset)`; `AgentRouter.route -> (str, agent)`; `run_task(agent_mode=)` recorded via EvalResult.skill_name; summarize_modes consumes the run_bank row shape it defines.
- Known judgment points for the implementer: SkillRouter private `_skills` access (add accessor if fragile); trigger label "book-itinerary" aliasing; routing-test phrasing adjustments allowed only for borderline scores.
