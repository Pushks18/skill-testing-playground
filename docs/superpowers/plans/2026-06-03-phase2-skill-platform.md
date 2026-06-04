# Phase 2: Skill Management Platform + Observability

**Goal:** Turn the CLI eval tool into a full platform — create and manage skills through a UI, observe every agent trajectory in detail, and classify failure modes to feed the optimizer.

**Builds on:** Week 1 MVP (A/B harness, gate check, leaderboard, task bank, optimizer)

**New tech:** Streamlit pages, LangSmith trace API, SQLite (trajectory store)

---

## New Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit UI (3 pages)                    │
│                                                              │
│  Page 1: Leaderboard    Page 2: Skill Manager   Page 3: Traces │
│  (exists, extend)       (new)                  (new)         │
└────────────┬────────────────────┬──────────────────┬─────────┘
             │                    │                  │
             ▼                    ▼                  ▼
      results/*.json       skills/ on disk    trajectory.db
      (eval results)       (SKILL.md files)   (SQLite, per-run)
             │                    │                  │
             └────────────────────┴──────────────────┘
                                  │
                         eval pipeline (existing)
                         LangSmith traces (existing)
```

---

## Module 1: Skill Management Platform

### What it does
A Streamlit page that replaces manually editing SKILL.md files. Covers:
- Browse existing skills (pyramid view: atomic / concrete / abstract)
- Create new skill with guided form
- Edit existing skill inline
- Submit skill for eval (triggers `ab_compare` as subprocess)
- View skill version history (git log per file)
- One-click optimizer run on a failing skill

### Files
```
ui/pages/2_Skill_Manager.py     # Streamlit page
eval/skill_manager.py           # Backend: read/write/validate SKILL.md, run git ops
```

### Skill Manager backend (`eval/skill_manager.py`)

```python
from dataclasses import dataclass
from pathlib import Path
import subprocess, re

SKILLS_DIR = Path("skills")
LAYERS = ["atomic", "concrete", "abstract"]

@dataclass
class SkillInfo:
    name: str
    layer: str
    path: Path
    content: str
    version: str          # latest git tag or commit hash
    last_modified: str    # git log date

def list_skills() -> list[SkillInfo]:
    """Return all skills from skills/ directory."""

def read_skill(layer: str, name: str) -> str:
    """Return SKILL.md content."""

def write_skill(layer: str, name: str, content: str) -> None:
    """Write SKILL.md. Validates format before writing."""

def validate_skill(content: str) -> list[str]:
    """Return list of validation errors. Empty = valid."""
    errors = []
    required = ["# ", "## When to Use", "## Workflow"]
    for r in required:
        if r not in content:
            errors.append(f"Missing section: {r}")
    return errors

def get_skill_history(layer: str, name: str) -> list[dict]:
    """Return git log for a skill file."""
    path = SKILLS_DIR / layer / name / "SKILL.md"
    result = subprocess.run(
        ["git", "log", "--oneline", "-10", str(path)],
        capture_output=True, text=True
    )
    return [{"hash": l[:7], "msg": l[8:]} for l in result.stdout.strip().split("\n") if l]

def run_eval(layer: str, name: str, trials: int = 3) -> str:
    """Run ab_compare for a skill, return output."""
    result = subprocess.run(
        ["python", "-m", "eval.ab_compare", "--skill", f"{layer}/{name}", "--trials", str(trials)],
        capture_output=True, text=True, cwd="."
    )
    return result.stdout + result.stderr
```

### Skill Manager UI (`ui/pages/2_Skill_Manager.py`)

Three tabs:
1. **Browse** — tree view of all skills by layer, click to view content + history + last eval score
2. **Edit / Create** — text area pre-filled with current SKILL.md, validate button, save + auto-commit
3. **Run Eval** — select skill, choose trials (3/5/10), run and stream output, show result inline

---

## Module 2: Agent Trajectory Observability

### What it does
Every agent run already posts to LangSmith. This module adds:
1. **Local trajectory store** — saves per-step data (node, tool, params, result, latency) to SQLite alongside the score
2. **Failure mode classifier** — analyzes failing runs and labels WHY they failed
3. **Trajectory viewer UI** — timeline of agent steps per task run

### Failure modes (taxonomy)
```
NO_TOOL_CALL        — agent responded without calling any tool
WRONG_TOOL          — called a tool not in required_tools
MISSING_PARAM       — called right tool but missing required param
WRONG_PARAM_VALUE   — called right tool, right params, but wrong values (e.g. wrong date format)
HALLUCINATED_ID     — used a made-up booking_id / flight_id
MULTI_STEP_DROPOUT  — completed step 1 but never reached step 2 (check_availability → create_booking)
PARTIAL_MATCH       — called some required tools but not all
```

### Files
```
eval/trajectory.py          # SQLite store + failure classifier
ui/pages/3_Trajectories.py  # Streamlit trajectory viewer
```

### Trajectory store (`eval/trajectory.py`)

```python
import sqlite3, json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DB_PATH = Path("trajectory.db")

@dataclass
class TrajectoryStep:
    run_id: str
    task_id: str
    skill_name: Optional[str]
    condition: str          # no_skill / with_skill
    step_num: int
    node: str               # agent / tools / format
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
    failure_mode: Optional[str]   # from taxonomy above
    steps: list[TrajectoryStep]
    langsmith_url: Optional[str]

def init_db():
    """Create tables if not exist."""

def save_run(run: TrajectoryRun):
    """Persist a run + its steps to SQLite."""

def get_runs(task_id: str = None, skill_name: str = None, failed_only: bool = False) -> list[TrajectoryRun]:
    """Query runs with optional filters."""

def classify_failure(run: TrajectoryRun, required_tools: list[str], required_params: dict) -> str:
    """
    Analyze a failing run and return the failure mode label.
    Logic:
    - No tools called at all → NO_TOOL_CALL
    - Tools called but none in required_tools → WRONG_TOOL  
    - Right tool called, missing param → MISSING_PARAM
    - Step 1 done, step 2 not done → MULTI_STEP_DROPOUT
    - Some required tools called but not all → PARTIAL_MATCH
    """
```

### Integration with run_task.py
`run_task()` already returns `EvalResult`. Extend it to also return trajectory steps by capturing tool calls with timestamps in the agent's `tool_node`. Save to SQLite after each run.

### Trajectory viewer UI (`ui/pages/3_Trajectories.py`)

Three views:
1. **Failure breakdown** — pie chart of failure modes across all runs, filterable by skill/domain
2. **Run timeline** — select a specific run_id, see step-by-step timeline: node → tool → params → result → latency
3. **Comparison** — side-by-side no_skill vs with_skill for same task: where does the skill change agent behavior?

---

## Module 3: Skill Form (guided creation)

The "Create" tab in Skill Manager uses a structured form instead of a raw text area for new skills, then generates the SKILL.md:

```
Fields:
  Name:           [text input]
  Layer:          [atomic / concrete / abstract]
  When to Use:    [text area — trigger phrases]
  Workflow steps: [dynamic list — add/remove steps]
  Tools used:     [multiselect from approved_tools.json]
  When NOT to use:[text area]
  Reuse refs:     [multiselect from existing skills]

→ [Generate SKILL.md] button → preview → [Save & Commit]
```

This enforces structure and prevents the missing-section validation errors seen in CI.

---

## Build Order (2 weeks)

### Week 2, Days 1-3: Trajectory observability
**Why first:** Failure mode data directly improves the optimizer — you can't tune skills without knowing WHY they fail.

1. `eval/trajectory.py` — SQLite store + `classify_failure()`
2. Instrument `agent/travel_agent.py` tool_node to capture per-step timing
3. Wire trajectory saving into `eval/run_task.py`
4. `ui/pages/3_Trajectories.py` — failure breakdown + run timeline

### Week 2, Days 4-5: Skill Management
**Why second:** Once you can see failure modes, you need a fast edit loop.

5. `eval/skill_manager.py` — read/write/validate/git ops
6. `ui/pages/2_Skill_Manager.py` — Browse + Edit tabs
7. Inline eval runner (subprocess, stream output to UI)
8. Skill creation form (structured → SKILL.md generator)

### Week 3: Polish + connect the loop
9. Connect failure modes → optimizer strategy auto-selection
10. Skill version comparison (diff view between two git commits)
11. LangSmith trace deep-link from trajectory viewer
12. Multi-model eval page (run same tasks against GPT-4.1-mini)

---

## Data Schemas (new)

```python
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
    steps: list[TrajectoryStep]
    langsmith_url: Optional[str]

@dataclass
class SkillInfo:
    name: str
    layer: str          # atomic / concrete / abstract
    path: Path
    content: str
    version: str
    last_modified: str
    last_eval_score: Optional[float]
    last_eval_regression_rate: Optional[float]
```

---

## Key Design Decisions

**SQLite over files for trajectories** — trajectories are queried (filter by failure_mode, skill, task), not just read. SQLite handles this; JSON files don't.

**Subprocess for eval runs from UI** — keeps the Streamlit process clean; avoids asyncio conflicts between Streamlit's event loop and LangGraph's.

**Git as skill version store** — don't build a custom version system. Every skill save is a git commit. History = `git log`. Diff = `git diff`. Rollback = `git checkout`.

**Failure classification is deterministic** — no LLM needed. Pure logic on the trajectory data. Fast and free.
