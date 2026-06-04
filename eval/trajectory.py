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
    "NO_TOOL_CALL",
    "WRONG_TOOL",
    "MISSING_PARAM",
    "MULTI_STEP_DROPOUT",
    "PARTIAL_MATCH",
    "HALLUCINATED_ID",
    "UNKNOWN",
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

    has_required = any(t in called_names for t in required_tools)

    if not has_required:
        return "WRONG_TOOL"

    if len(required_tools) > 1:
        done = [t for t in required_tools if t in called_names]
        if len(done) < len(required_tools):
            # MULTI_STEP_DROPOUT: required_params specified (structure aware)
            # PARTIAL_MATCH: no required_params (structure agnostic)
            if required_params:
                return "MULTI_STEP_DROPOUT"
            else:
                return "PARTIAL_MATCH"

    for tool_name, params in required_params.items():
        if tool_name in called_names:
            for p in params:
                if p not in called_params.get(tool_name, {}):
                    return "MISSING_PARAM"

    return None
