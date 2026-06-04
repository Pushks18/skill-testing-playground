# Phase 2: Trajectory Observability + Skill Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-run trajectory storage with deterministic failure classification, a trajectory viewer UI, and a skill management UI with inline editing and one-click eval.

**Architecture:** `eval/trajectory.py` stores every tool call to SQLite alongside `EvalResult`; `agent/travel_agent.py` is instrumented to emit per-step timing; `eval/run_task.py` saves the trajectory after each run; two Streamlit pages expose the data. The skill manager reads/writes SKILL.md files on disk and shells out to `ab_compare` for eval runs.

**Tech Stack:** Python 3.11, SQLite (stdlib), Streamlit, pandas, subprocess, existing LangGraph agent

---

## File Map

```
eval/trajectory.py              NEW  SQLite store + failure classifier + TrajectoryRun/Step dataclasses
agent/travel_agent.py           MOD  tool_node emits per-step timing; build_travel_agent accepts callbacks
eval/run_task.py                MOD  save TrajectoryRun to SQLite after every run
eval/skill_manager.py           NEW  read/write/validate SKILL.md + git ops + subprocess eval runner
tests/test_trajectory.py        NEW  unit tests for failure classifier + DB round-trip
tests/test_skill_manager.py     NEW  unit tests for validate_skill + list_skills
ui/pages/                       NEW  directory (Streamlit multi-page)
ui/pages/2_Skill_Manager.py     NEW  browse/edit/create/eval tabs
ui/pages/3_Trajectories.py      NEW  failure pie chart + run timeline + no-skill vs with-skill diff
```

---

## Part A: Trajectory Observability

---

### Task 1: Trajectory dataclasses + SQLite store

**Files:**
- Create: `eval/trajectory.py`
- Create: `tests/test_trajectory.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_trajectory.py
import pytest, uuid, pathlib, tempfile, os
from eval.trajectory import (
    TrajectoryStep, TrajectoryRun, init_db, save_run, get_runs,
    classify_failure, FAILURE_MODES,
)

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "test_trajectory.db"
    monkeypatch.setattr("eval.trajectory.DB_PATH", db)
    init_db()
    return db

def make_run(tools_called=None, score=1.0, passed=True, failure_mode=None):
    run_id = str(uuid.uuid4())
    steps = []
    for i, t in enumerate(tools_called or []):
        steps.append(TrajectoryStep(
            run_id=run_id, task_id="t1", skill_name="test", condition="with_skill",
            step_num=i, node="tools", tool_name=t["name"],
            tool_params=t.get("params", {}), tool_result="ok",
            latency_ms=50, tokens=10,
        ))
    return TrajectoryRun(
        run_id=run_id, task_id="t1", skill_name="test", condition="with_skill",
        score=score, passed=passed, failure_mode=failure_mode, steps=steps,
        langsmith_url=None,
    )

def test_save_and_retrieve(tmp_db):
    run = make_run(tools_called=[{"name": "search_flights", "params": {"origin": "JFK"}}])
    save_run(run)
    runs = get_runs(task_id="t1")
    assert len(runs) == 1
    assert runs[0].run_id == run.run_id
    assert len(runs[0].steps) == 1
    assert runs[0].steps[0].tool_name == "search_flights"

def test_filter_failed_only(tmp_db):
    save_run(make_run(score=1.0, passed=True))
    save_run(make_run(score=0.0, passed=False, failure_mode="NO_TOOL_CALL"))
    all_runs = get_runs(task_id="t1")
    failed = get_runs(task_id="t1", failed_only=True)
    assert len(all_runs) == 2
    assert len(failed) == 1
    assert failed[0].failure_mode == "NO_TOOL_CALL"

def test_classify_no_tool_call():
    mode = classify_failure(
        tools_called=[], required_tools=["search_flights"], required_params={}
    )
    assert mode == "NO_TOOL_CALL"

def test_classify_wrong_tool():
    mode = classify_failure(
        tools_called=[{"name": "get_itinerary", "params": {}}],
        required_tools=["search_flights"], required_params={}
    )
    assert mode == "WRONG_TOOL"

def test_classify_missing_param():
    mode = classify_failure(
        tools_called=[{"name": "search_flights", "params": {"origin": "JFK"}}],
        required_tools=["search_flights"],
        required_params={"search_flights": ["origin", "destination", "date"]}
    )
    assert mode == "MISSING_PARAM"

def test_classify_multi_step_dropout():
    mode = classify_failure(
        tools_called=[{"name": "check_availability", "params": {"resource_id": "FL1", "date": "2026-07-01"}}],
        required_tools=["check_availability", "create_booking"],
        required_params={"check_availability": ["resource_id", "date"], "create_booking": ["flight_id", "passenger"]}
    )
    assert mode == "MULTI_STEP_DROPOUT"

def test_classify_partial_match():
    mode = classify_failure(
        tools_called=[{"name": "search_flights", "params": {"origin": "JFK", "destination": "LAX", "date": "2026-07-01"}}],
        required_tools=["search_flights", "search_hotels"],
        required_params={}
    )
    assert mode == "PARTIAL_MATCH"

def test_classify_no_failure_on_pass():
    mode = classify_failure(
        tools_called=[{"name": "search_flights", "params": {"origin": "JFK", "destination": "LAX", "date": "2026-07-01"}}],
        required_tools=["search_flights"],
        required_params={"search_flights": ["origin", "destination", "date"]}
    )
    assert mode is None
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd /Users/pushkaraj/Documents/skill-testing-playground
.venv/bin/python3.11 -m pytest tests/test_trajectory.py -v 2>&1 | head -20
```

- [ ] **Step 3: Create `eval/trajectory.py`**

```python
# eval/trajectory.py
"""SQLite trajectory store and deterministic failure mode classifier."""
from __future__ import annotations
import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DB_PATH = Path("trajectory.db")

FAILURE_MODES = [
    "NO_TOOL_CALL",       # agent returned no tool calls
    "WRONG_TOOL",         # called a tool not in required_tools
    "MISSING_PARAM",      # right tool, missing required param
    "MULTI_STEP_DROPOUT", # first step done, second step not done
    "PARTIAL_MATCH",      # some required tools called, not all
    "HALLUCINATED_ID",    # booking/flight ID looks fabricated (not from context)
    "UNKNOWN",            # failed but pattern unrecognised
]


@dataclass
class TrajectoryStep:
    run_id: str
    task_id: str
    skill_name: Optional[str]
    condition: str
    step_num: int
    node: str
    tool_name: Optional[str]
    tool_params: Optional[dict]
    tool_result: Optional[str]
    latency_ms: int
    tokens: int


@dataclass
class TrajectoryRun:
    run_id: str
    task_id: str
    skill_name: Optional[str]
    condition: str
    score: float
    passed: bool
    failure_mode: Optional[str]
    steps: list
    langsmith_url: Optional[str]


def init_db(db_path: Path = None):
    path = db_path or DB_PATH
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            task_id TEXT,
            skill_name TEXT,
            condition TEXT,
            score REAL,
            passed INTEGER,
            failure_mode TEXT,
            langsmith_url TEXT
        );
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            task_id TEXT,
            skill_name TEXT,
            condition TEXT,
            step_num INTEGER,
            node TEXT,
            tool_name TEXT,
            tool_params TEXT,
            tool_result TEXT,
            latency_ms INTEGER,
            tokens INTEGER,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);
        CREATE INDEX IF NOT EXISTS idx_runs_skill ON runs(skill_name);
        CREATE INDEX IF NOT EXISTS idx_steps_run ON steps(run_id);
    """)
    con.commit()
    con.close()


def save_run(run: TrajectoryRun, db_path: Path = None):
    path = db_path or DB_PATH
    if not path.exists():
        init_db(path)
    con = sqlite3.connect(path)
    con.execute(
        "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?)",
        (run.run_id, run.task_id, run.skill_name, run.condition,
         run.score, int(run.passed), run.failure_mode, run.langsmith_url)
    )
    for s in run.steps:
        con.execute(
            "INSERT INTO steps (run_id,task_id,skill_name,condition,step_num,node,"
            "tool_name,tool_params,tool_result,latency_ms,tokens) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (s.run_id, s.task_id, s.skill_name, s.condition, s.step_num, s.node,
             s.tool_name, json.dumps(s.tool_params) if s.tool_params else None,
             s.tool_result, s.latency_ms, s.tokens)
        )
    con.commit()
    con.close()


def get_runs(
    task_id: str = None,
    skill_name: str = None,
    failed_only: bool = False,
    db_path: Path = None,
    limit: int = 200,
) -> list:
    path = db_path or DB_PATH
    if not path.exists():
        return []
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row

    where, params = [], []
    if task_id:
        where.append("r.task_id = ?"); params.append(task_id)
    if skill_name:
        where.append("r.skill_name = ?"); params.append(skill_name)
    if failed_only:
        where.append("r.passed = 0")
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    rows = con.execute(
        f"SELECT * FROM runs r {where_clause} ORDER BY rowid DESC LIMIT ?",
        params + [limit]
    ).fetchall()

    results = []
    for row in rows:
        step_rows = con.execute(
            "SELECT * FROM steps WHERE run_id = ? ORDER BY step_num",
            (row["run_id"],)
        ).fetchall()
        steps = [
            TrajectoryStep(
                run_id=s["run_id"], task_id=s["task_id"], skill_name=s["skill_name"],
                condition=s["condition"], step_num=s["step_num"], node=s["node"],
                tool_name=s["tool_name"],
                tool_params=json.loads(s["tool_params"]) if s["tool_params"] else None,
                tool_result=s["tool_result"], latency_ms=s["latency_ms"], tokens=s["tokens"],
            )
            for s in step_rows
        ]
        results.append(TrajectoryRun(
            run_id=row["run_id"], task_id=row["task_id"], skill_name=row["skill_name"],
            condition=row["condition"], score=row["score"], passed=bool(row["passed"]),
            failure_mode=row["failure_mode"], steps=steps, langsmith_url=row["langsmith_url"],
        ))
    con.close()
    return results


def classify_failure(
    tools_called: list,
    required_tools: list,
    required_params: dict,
) -> Optional[str]:
    """Deterministic failure classification. Returns None if no failure."""
    called_names = [t["name"] for t in tools_called]
    called_params = {t["name"]: t.get("params", {}) for t in tools_called}

    if not called_names:
        return "NO_TOOL_CALL"

    if not any(t in called_names for t in required_tools):
        return "WRONG_TOOL"

    # Multi-step: required tools are a sequence and first was done but not last
    if len(required_tools) > 1:
        done = [t for t in required_tools if t in called_names]
        if len(done) < len(required_tools):
            if done:
                return "MULTI_STEP_DROPOUT"
            return "PARTIAL_MATCH"

    # Single required tool: check params
    for tool_name, params in required_params.items():
        if tool_name in called_names:
            for p in params:
                if p not in called_params.get(tool_name, {}):
                    return "MISSING_PARAM"

    return None
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
cd /Users/pushkaraj/Documents/skill-testing-playground
.venv/bin/python3.11 -m pytest tests/test_trajectory.py -v
```

Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
git add eval/trajectory.py tests/test_trajectory.py
git commit -m "feat: trajectory SQLite store and failure mode classifier"
```

---

### Task 2: Instrument agent + wire trajectory into run_task

**Files:**
- Modify: `agent/travel_agent.py` — tool_node records per-step timing
- Modify: `eval/run_task.py` — save TrajectoryRun after each run

- [ ] **Step 1: Add `step_timings` to AgentState and instrument tool_node**

In `agent/travel_agent.py`, add `step_timings: list` to `AgentState` and capture latency per tool call in `tool_node`. Replace the existing `tool_node` and `AgentState`:

```python
# agent/travel_agent.py  — replace AgentState and tool_node only

import time as _time   # add this import at top

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    tools_called: list
    step_timings: list   # NEW: list of {"tool": str, "latency_ms": int, "tokens": int}
    response: str
    steps: int
    tokens_used: int

# Replace tool_node:
def tool_node(state: AgentState) -> dict:
    last = state["messages"][-1]
    tool_results = []
    tools_called = list(state.get("tools_called", []))
    step_timings = list(state.get("step_timings", []))
    for tc in getattr(last, "tool_calls", []):
        fn = tool_map.get(tc["name"])
        if fn:
            t0 = _time.time()
            result = fn.invoke(tc["args"])
            latency = int((_time.time() - t0) * 1000)
            tools_called.append({"name": tc["name"], "params": tc["args"]})
            step_timings.append({"tool": tc["name"], "latency_ms": latency, "tokens": 0})
            tool_results.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
    return {"messages": tool_results, "tools_called": tools_called, "step_timings": step_timings}
```

Also update `agent_node` to pass through `step_timings`:

```python
def agent_node(state: AgentState) -> dict:
    msgs = [SystemMessage(content=system_prompt)] + state["messages"]
    response = llm.invoke(msgs)
    steps = state.get("steps", 0) + 1
    usage = getattr(response, "usage_metadata", None) or {}
    tokens = state.get("tokens_used", 0) + usage.get("total_tokens", 0)
    return {
        "messages": [response],
        "tools_called": state.get("tools_called", []),
        "step_timings": state.get("step_timings", []),
        "steps": steps,
        "tokens_used": tokens,
    }
```

Update the `agent.invoke(...)` call in `run_task.py` to include `step_timings: []` in the initial state:

```python
result = agent.invoke({
    "messages": [{"role": "user", "content": task["instruction"]}],
    "tools_called": [],
    "step_timings": [],
    "response": "",
    "steps": 0,
    "tokens_used": 0,
})
```

- [ ] **Step 2: Wire trajectory saving into `eval/run_task.py`**

Add these imports at the top of `run_task.py`:

```python
import uuid
from eval.trajectory import (
    TrajectoryRun, TrajectoryStep, save_run, classify_failure, init_db
)
```

Replace the `return EvalResult(...)` block in `run_task()` with:

```python
    eval_result = EvalResult(
        task_id=task["id"],
        domain=task["domain"],
        skill_name=task.get("skill") if skill_path else None,
        skill_version=None,
        score=vresult.score,
        steps=result.get("steps", 0),
        tools_called=[t["name"] for t in result.get("tools_called", [])],
        tool_params={t["name"]: t.get("params", {}) for t in result.get("tools_called", [])},
        langsmith_run_id="",
        passed_verifier=vresult.passed,
        judge_reasoning=vresult.reason,
        latency_ms=latency_ms,
        tokens_used=result.get("tokens_used", 0),
    )

    # Save trajectory
    run_id = str(uuid.uuid4())
    tools_called_raw = result.get("tools_called", [])
    failure_mode = None
    if not vresult.passed:
        failure_mode = classify_failure(
            tools_called=tools_called_raw,
            required_tools=expected.get("tools", []),
            required_params=expected.get("required_params", {}),
        )

    steps_data = []
    for i, timing in enumerate(result.get("step_timings", [])):
        steps_data.append(TrajectoryStep(
            run_id=run_id, task_id=task["id"],
            skill_name=eval_result.skill_name,
            condition=condition, step_num=i, node="tools",
            tool_name=timing.get("tool"),
            tool_params=tools_called_raw[i].get("params") if i < len(tools_called_raw) else None,
            tool_result=None,
            latency_ms=timing.get("latency_ms", 0),
            tokens=timing.get("tokens", 0),
        ))

    trajectory = TrajectoryRun(
        run_id=run_id, task_id=task["id"],
        skill_name=eval_result.skill_name,
        condition=condition, score=vresult.score,
        passed=vresult.passed, failure_mode=failure_mode,
        steps=steps_data, langsmith_url=None,
    )
    try:
        save_run(trajectory)
    except Exception:
        pass  # trajectory is observability; never fail an eval run because of it

    return eval_result
```

- [ ] **Step 3: Run the existing test suite — confirm nothing broke**

```bash
cd /Users/pushkaraj/Documents/skill-testing-playground
.venv/bin/python3.11 -m pytest tests/test_schemas.py tests/test_verifiers.py tests/test_gate_check.py tests/test_trajectory.py -v 2>&1 | tail -15
```

Expected: all PASS (trajectory.db will be created in project root)

- [ ] **Step 4: Smoke test — run one task and confirm trajectory.db is written**

```bash
# terminal 1 — start mock MCP if not running
python3 eval/mock_mcp/server.py &

# terminal 2
cd /Users/pushkaraj/Documents/skill-testing-playground
.venv/bin/python3.11 -c "
from eval.run_task import run_task
r = run_task('tasks/flight-search-001', None, 'no_skill')
print('score:', r.score)
from eval.trajectory import get_runs
runs = get_runs(task_id='flight-search-001')
print('trajectory runs:', len(runs))
print('steps:', len(runs[0].steps) if runs else 0)
print('failure_mode:', runs[0].failure_mode if runs else None)
"
```

Expected output:
```
score: 1.0
trajectory runs: 1
steps: 1
failure_mode: None
```

- [ ] **Step 5: Commit**

```bash
git add agent/travel_agent.py eval/run_task.py
git commit -m "feat: instrument agent tool_node with per-step timing + wire trajectory into run_task"
```

---

### Task 3: Trajectory viewer UI

**Files:**
- Create: `ui/pages/3_Trajectories.py`

- [ ] **Step 1: Create `ui/pages/` directory and `ui/pages/3_Trajectories.py`**

```python
# ui/pages/3_Trajectories.py
"""Trajectory viewer: failure breakdown + per-run step timeline."""
from __future__ import annotations
import pathlib
import sys

import pandas as pd
import streamlit as st

# Make project root importable when streamlit runs from project root
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

from eval.trajectory import get_runs, FAILURE_MODES, TrajectoryRun

st.set_page_config(page_title="Trajectories", layout="wide")
st.title("Agent Trajectory Viewer")

DB = pathlib.Path("trajectory.db")
if not DB.exists():
    st.warning("No trajectory data yet. Run `python -m eval.ab_compare` first.")
    st.stop()

# --- Sidebar filters ---
st.sidebar.header("Filters")
skill_filter = st.sidebar.text_input("Skill name (leave blank for all)", "")
task_filter = st.sidebar.text_input("Task ID (leave blank for all)", "")
failed_only = st.sidebar.checkbox("Failed runs only", value=False)

runs: list[TrajectoryRun] = get_runs(
    skill_name=skill_filter or None,
    task_id=task_filter or None,
    failed_only=failed_only,
    limit=500,
)

if not runs:
    st.info("No runs match the current filters.")
    st.stop()

# --- Tab layout ---
tab1, tab2, tab3 = st.tabs(["Failure Breakdown", "Run Timeline", "No-Skill vs With-Skill"])

# ── Tab 1: Failure breakdown ──────────────────────────────────────────────────
with tab1:
    st.subheader(f"Failure breakdown ({len(runs)} runs)")

    failed_runs = [r for r in runs if not r.passed]
    passed_runs = [r for r in runs if r.passed]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total runs", len(runs))
    col2.metric("Passed", len(passed_runs))
    col3.metric("Failed", len(failed_runs))

    if failed_runs:
        from collections import Counter
        mode_counts = Counter(r.failure_mode or "UNKNOWN" for r in failed_runs)
        mode_df = pd.DataFrame([
            {"Failure Mode": k, "Count": v, "% of failures": f"{v/len(failed_runs):.0%}"}
            for k, v in sorted(mode_counts.items(), key=lambda x: -x[1])
        ])
        st.dataframe(mode_df, use_container_width=True, hide_index=True)
        st.bar_chart(mode_df.set_index("Failure Mode")["Count"])

        st.subheader("Failed run details")
        fail_rows = []
        for r in failed_runs:
            fail_rows.append({
                "Run ID": r.run_id[:8],
                "Task": r.task_id,
                "Skill": r.skill_name or "—",
                "Condition": r.condition,
                "Score": round(r.score, 2),
                "Failure Mode": r.failure_mode or "UNKNOWN",
                "Steps": len(r.steps),
            })
        st.dataframe(pd.DataFrame(fail_rows), use_container_width=True, hide_index=True)
    else:
        st.success("No failures in current filter set.")

# ── Tab 2: Run timeline ───────────────────────────────────────────────────────
with tab2:
    st.subheader("Step-by-step timeline")

    run_ids = [f"{r.run_id[:8]} | {r.task_id} | {r.condition} | score={r.score:.2f}" for r in runs]
    selected_label = st.selectbox("Select run", run_ids)
    selected_idx = run_ids.index(selected_label)
    selected_run = runs[selected_idx]

    status = "✅ PASSED" if selected_run.passed else f"❌ FAILED — {selected_run.failure_mode or 'UNKNOWN'}"
    st.markdown(f"**Status:** {status}  |  **Score:** {selected_run.score:.2f}  |  **Total steps:** {len(selected_run.steps)}")

    if selected_run.steps:
        step_rows = []
        for s in selected_run.steps:
            step_rows.append({
                "Step": s.step_num,
                "Node": s.node,
                "Tool": s.tool_name or "—",
                "Params": str(s.tool_params) if s.tool_params else "—",
                "Latency (ms)": s.latency_ms,
                "Tokens": s.tokens,
            })
        st.dataframe(pd.DataFrame(step_rows), use_container_width=True, hide_index=True)

        if len(step_rows) > 1:
            latency_df = pd.DataFrame(step_rows).set_index("Step")["Latency (ms)"]
            st.bar_chart(latency_df)
    else:
        st.info("No tool steps recorded (agent responded without calling tools).")

# ── Tab 3: No-skill vs With-skill diff ────────────────────────────────────────
with tab3:
    st.subheader("No-skill vs with-skill comparison")

    task_ids = sorted(set(r.task_id for r in runs))
    selected_task = st.selectbox("Select task", task_ids)

    no_skill_runs = [r for r in runs if r.task_id == selected_task and r.condition == "no_skill"]
    with_skill_runs = [r for r in runs if r.task_id == selected_task and r.condition == "with_skill"]

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Without skill**")
        if no_skill_runs:
            r = no_skill_runs[0]
            st.metric("Score", round(r.score, 2))
            st.metric("Steps", len(r.steps))
            st.metric("Status", "PASS" if r.passed else f"FAIL: {r.failure_mode}")
            tools_used = [s.tool_name for s in r.steps if s.tool_name]
            st.write("Tools called:", tools_used or ["none"])
        else:
            st.info("No no-skill runs for this task.")

    with col_b:
        st.markdown("**With skill**")
        if with_skill_runs:
            r = with_skill_runs[0]
            st.metric("Score", round(r.score, 2))
            st.metric("Steps", len(r.steps))
            st.metric("Status", "PASS" if r.passed else f"FAIL: {r.failure_mode}")
            tools_used = [s.tool_name for s in r.steps if s.tool_name]
            st.write("Tools called:", tools_used or ["none"])
        else:
            st.info("No with-skill runs for this task.")
```

- [ ] **Step 2: Verify it imports without error**

```bash
cd /Users/pushkaraj/Documents/skill-testing-playground
.venv/bin/python3.11 -c "import ast; ast.parse(open('ui/pages/3_Trajectories.py').read()); print('syntax OK')"
```

- [ ] **Step 3: Run some evals to generate trajectory data, then launch UI**

```bash
# Start mock MCP if not running
python3 eval/mock_mcp/server.py &

# Run evals to populate trajectory.db
.venv/bin/python3.11 -m eval.ab_compare --skill concrete/flight-search --trials 2
.venv/bin/python3.11 -m eval.ab_compare --skill abstract/book-itinerary --trials 2

# Launch UI
.venv/bin/python3.11 -m streamlit run ui/app.py
```

Navigate to the Trajectories page and confirm failure breakdown and timeline render.

- [ ] **Step 4: Commit**

```bash
git add ui/pages/3_Trajectories.py
git commit -m "feat: trajectory viewer UI — failure breakdown, run timeline, no-skill vs with-skill diff"
```

---

## Part B: Skill Management Platform

---

### Task 4: Skill manager backend

**Files:**
- Create: `eval/skill_manager.py`
- Create: `tests/test_skill_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_skill_manager.py
import pytest, pathlib, tempfile, shutil
from eval.skill_manager import (
    validate_skill, list_skills, read_skill, write_skill, SkillInfo
)

VALID_SKILL = """# test-skill

## When to Use
When user asks about tests.

## Workflow
1. Do the thing
2. Return the result

## When NOT to Use
- Never in production
"""

INVALID_SKILL_MISSING_WORKFLOW = """# test-skill

## When to Use
When user asks about tests.
"""

@pytest.fixture
def skill_dir(tmp_path):
    (tmp_path / "concrete" / "test-skill").mkdir(parents=True)
    (tmp_path / "concrete" / "test-skill" / "SKILL.md").write_text(VALID_SKILL)
    (tmp_path / "atomic").mkdir()
    (tmp_path / "abstract").mkdir()
    return tmp_path

def test_validate_valid():
    errors = validate_skill(VALID_SKILL)
    assert errors == []

def test_validate_missing_workflow():
    errors = validate_skill(INVALID_SKILL_MISSING_WORKFLOW)
    assert any("Workflow" in e for e in errors)

def test_list_skills(skill_dir):
    skills = list_skills(skills_dir=skill_dir)
    assert len(skills) == 1
    assert skills[0].name == "test-skill"
    assert skills[0].layer == "concrete"

def test_read_skill(skill_dir):
    content = read_skill("concrete", "test-skill", skills_dir=skill_dir)
    assert "## When to Use" in content

def test_write_skill(skill_dir):
    new_content = VALID_SKILL.replace("Do the thing", "Do the other thing")
    write_skill("concrete", "test-skill", new_content, skills_dir=skill_dir)
    assert "Do the other thing" in read_skill("concrete", "test-skill", skills_dir=skill_dir)

def test_write_skill_rejects_invalid(skill_dir):
    with pytest.raises(ValueError, match="Workflow"):
        write_skill("concrete", "test-skill", INVALID_SKILL_MISSING_WORKFLOW, skills_dir=skill_dir)
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd /Users/pushkaraj/Documents/skill-testing-playground
.venv/bin/python3.11 -m pytest tests/test_skill_manager.py -v 2>&1 | head -20
```

- [ ] **Step 3: Create `eval/skill_manager.py`**

```python
# eval/skill_manager.py
"""Read, write, validate SKILL.md files and shell out to git + eval."""
from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path("skills")
LAYERS = ["atomic", "concrete", "abstract"]
REQUIRED_SECTIONS = ["# ", "## When to Use", "## Workflow"]


@dataclass
class SkillInfo:
    name: str
    layer: str
    path: Path
    content: str
    last_commit: str       # short hash from git log
    last_modified: str     # date string from git log
    last_eval_score: Optional[float] = None
    last_regression_rate: Optional[float] = None


def validate_skill(content: str) -> list[str]:
    """Return list of validation errors. Empty list = valid."""
    errors = []
    for section in REQUIRED_SECTIONS:
        if section not in content:
            errors.append(f"Missing required section: '{section}'")
    if len(content.strip()) < 50:
        errors.append("Skill content too short (< 50 chars)")
    return errors


def list_skills(skills_dir: Path = None) -> list[SkillInfo]:
    root = skills_dir or SKILLS_DIR
    result = []
    for layer in LAYERS:
        layer_dir = root / layer
        if not layer_dir.exists():
            continue
        for skill_dir in sorted(layer_dir.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            commit, date = _git_log(skill_file)
            result.append(SkillInfo(
                name=skill_dir.name,
                layer=layer,
                path=skill_file,
                content=skill_file.read_text(),
                last_commit=commit,
                last_modified=date,
            ))
    return result


def read_skill(layer: str, name: str, skills_dir: Path = None) -> str:
    root = skills_dir or SKILLS_DIR
    return (root / layer / name / "SKILL.md").read_text()


def write_skill(layer: str, name: str, content: str, skills_dir: Path = None):
    errors = validate_skill(content)
    if errors:
        raise ValueError("; ".join(errors))
    root = skills_dir or SKILLS_DIR
    path = root / layer / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def commit_skill(layer: str, name: str, message: str = None) -> str:
    """Git add + commit a skill file. Returns commit hash."""
    path = SKILLS_DIR / layer / name / "SKILL.md"
    msg = message or f"feat: update skill {name}"
    subprocess.run(["git", "add", str(path)], check=True)
    result = subprocess.run(
        ["git", "commit", "-m", msg],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return result.stderr.strip()
    return result.stdout.strip().split("\n")[0]


def get_skill_history(layer: str, name: str) -> list[dict]:
    """Return last 10 git commits for a skill file."""
    path = SKILLS_DIR / layer / name / "SKILL.md"
    result = subprocess.run(
        ["git", "log", "--oneline", "-10", "--", str(path)],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        return []
    return [
        {"hash": line[:7], "message": line[8:]}
        for line in result.stdout.strip().split("\n")
        if line
    ]


def run_eval(layer: str, name: str, trials: int = 3) -> str:
    """Run ab_compare for a skill synchronously. Returns combined stdout+stderr."""
    result = subprocess.run(
        [".venv/bin/python3.11", "-m", "eval.ab_compare",
         "--skill", f"{layer}/{name}", "--trials", str(trials)],
        capture_output=True, text=True, cwd="."
    )
    return result.stdout + result.stderr


def load_last_eval_results(name: str) -> Optional[dict]:
    """Load the most recent ab_results JSON for a skill."""
    path = Path("results") / f"{name}_ab_results.json"
    if not path.exists():
        return None
    import json
    data = json.loads(path.read_text())
    if not data:
        return None
    total_w = sum(r.get("task_weight", 1.0) for r in data)
    weighted_delta = sum(r["delta"] * r.get("task_weight", 1.0) for r in data) / total_w
    regression_rate = sum(1 for r in data if r["delta"] < 0) / len(data)
    return {"weighted_delta": round(weighted_delta, 3), "regression_rate": round(regression_rate, 2)}


def _git_log(path: Path) -> tuple[str, str]:
    result = subprocess.run(
        ["git", "log", "--format=%h|%ad", "--date=short", "-1", "--", str(path)],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        parts = result.stdout.strip().split("|")
        return parts[0], parts[1] if len(parts) > 1 else ""
    return "—", "—"
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/pushkaraj/Documents/skill-testing-playground
.venv/bin/python3.11 -m pytest tests/test_skill_manager.py -v
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add eval/skill_manager.py tests/test_skill_manager.py
git commit -m "feat: skill manager backend — read/write/validate/git ops"
```

---

### Task 5: Skill Manager UI

**Files:**
- Create: `ui/pages/2_Skill_Manager.py`

- [ ] **Step 1: Create `ui/pages/2_Skill_Manager.py`**

```python
# ui/pages/2_Skill_Manager.py
"""Skill management UI: browse, edit, create, and run evals."""
from __future__ import annotations
import pathlib
import sys

import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

from eval.skill_manager import (
    list_skills, read_skill, write_skill, commit_skill,
    get_skill_history, run_eval, load_last_eval_results,
    validate_skill, LAYERS,
)

st.set_page_config(page_title="Skill Manager", layout="wide")
st.title("Skill Manager")

tab1, tab2, tab3 = st.tabs(["Browse", "Edit / Create", "Run Eval"])

# ── Tab 1: Browse ─────────────────────────────────────────────────────────────
with tab1:
    st.subheader("Skill Library")
    skills = list_skills()

    if not skills:
        st.warning("No skills found in skills/ directory.")
    else:
        for layer in LAYERS:
            layer_skills = [s for s in skills if s.layer == layer]
            if not layer_skills:
                continue
            st.markdown(f"### {layer.capitalize()} ({len(layer_skills)})")
            for skill in layer_skills:
                eval_data = load_last_eval_results(skill.name)
                delta_str = f"Δ {eval_data['weighted_delta']:+.3f}" if eval_data else "not evaluated"
                regr_str = f" | regr {eval_data['regression_rate']:.0%}" if eval_data else ""
                with st.expander(f"**{skill.name}** — {delta_str}{regr_str} — last commit: {skill.last_commit} ({skill.last_modified})"):
                    st.code(skill.content, language="markdown")
                    history = get_skill_history(skill.layer, skill.name)
                    if history:
                        st.markdown("**Recent commits:**")
                        for h in history:
                            st.markdown(f"- `{h['hash']}` {h['message']}")

# ── Tab 2: Edit / Create ──────────────────────────────────────────────────────
with tab2:
    st.subheader("Edit or Create a Skill")

    col1, col2 = st.columns([1, 3])
    with col1:
        mode = st.radio("Mode", ["Edit existing", "Create new"])
        selected_layer = st.selectbox("Layer", LAYERS)

    if mode == "Edit existing":
        layer_skills = [s for s in list_skills() if s.layer == selected_layer]
        if not layer_skills:
            st.info(f"No {selected_layer} skills yet.")
            st.stop()
        skill_names = [s.name for s in layer_skills]
        with col1:
            selected_name = st.selectbox("Skill", skill_names)
        initial_content = read_skill(selected_layer, selected_name)
    else:
        with col1:
            selected_name = st.text_input("New skill name (e.g. car-rental)")
        initial_content = f"# {selected_name or 'new-skill'}\n\n## When to Use\n\n## Workflow\n1. \n\n## When NOT to Use\n- \n"

    with col2:
        edited_content = st.text_area(
            "SKILL.md content",
            value=initial_content,
            height=450,
            key=f"editor_{selected_layer}_{selected_name}",
        )
        errors = validate_skill(edited_content)
        if errors:
            for e in errors:
                st.error(f"Validation: {e}")
        else:
            st.success("Format valid")

        commit_msg = st.text_input("Commit message", value=f"feat: update skill {selected_name}")
        save_col, _ = st.columns([1, 3])
        with save_col:
            if st.button("Save & Commit", disabled=bool(errors) or not selected_name):
                try:
                    write_skill(selected_layer, selected_name, edited_content)
                    result = commit_skill(selected_layer, selected_name, commit_msg)
                    st.success(f"Saved and committed: {result}")
                except Exception as exc:
                    st.error(str(exc))

# ── Tab 3: Run Eval ───────────────────────────────────────────────────────────
with tab3:
    st.subheader("Run A/B Eval")

    skills = list_skills()
    if not skills:
        st.info("No skills found.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            eval_layer = st.selectbox("Layer ", LAYERS, key="eval_layer")
        with col2:
            layer_skills = [s.name for s in skills if s.layer == eval_layer]
            eval_skill = st.selectbox("Skill ", layer_skills, key="eval_skill") if layer_skills else None
        with col3:
            trials = st.selectbox("Trials", [2, 3, 5, 10], index=1)

        if eval_skill and st.button(f"Run eval: {eval_layer}/{eval_skill} (N={trials})"):
            with st.spinner(f"Running A/B eval for {eval_skill}..."):
                output = run_eval(eval_layer, eval_skill, trials)
            st.code(output, language="text")

            eval_data = load_last_eval_results(eval_skill)
            if eval_data:
                c1, c2 = st.columns(2)
                c1.metric("Weighted Δ", f"{eval_data['weighted_delta']:+.3f}")
                c2.metric("Regression Rate", f"{eval_data['regression_rate']:.0%}")
```

- [ ] **Step 2: Verify syntax**

```bash
.venv/bin/python3.11 -c "import ast; ast.parse(open('ui/pages/2_Skill_Manager.py').read()); print('syntax OK')"
```

- [ ] **Step 3: Launch full UI and verify all 3 pages load**

```bash
.venv/bin/python3.11 -m streamlit run ui/app.py
```

Navigate to:
- Page 1 (Leaderboard): should show skill summary table
- Page 2 (Skill Manager): should show Browse tab with 4 skills
- Page 3 (Trajectories): should show failure breakdown

- [ ] **Step 4: Commit**

```bash
git add ui/pages/2_Skill_Manager.py
git commit -m "feat: skill manager UI — browse, edit/create, one-click eval runner"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Task |
|-----------------|------|
| SQLite trajectory store | Task 1 |
| 7-type failure classifier | Task 1 |
| Per-step timing in agent | Task 2 |
| Wire trajectory into run_task | Task 2 |
| Failure breakdown UI | Task 3 |
| Run timeline UI | Task 3 |
| No-skill vs with-skill diff | Task 3 |
| `eval/skill_manager.py` read/write/validate/git | Task 4 |
| Browse skills by layer | Task 5 |
| Edit inline with validation | Task 5 |
| One-click eval runner | Task 5 |

### Type consistency check
- `TrajectoryStep` and `TrajectoryRun` defined in Task 1, used identically in Tasks 2 and 3 ✓
- `SkillInfo` defined in Task 4, used in Task 5 ✓
- `get_runs()` signature in Task 1 matches calls in Task 3 ✓
- `classify_failure(tools_called, required_tools, required_params)` signature matches test calls ✓
- `run_eval(layer, name, trials)` in Task 4 matches Task 5 call ✓
