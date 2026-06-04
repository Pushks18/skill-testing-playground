"""Tests for Phase 6.2: GRPO auto-proposal pipeline."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from eval.optimizer.propose_skill import (
    FailureCluster,
    build_frontmatter,
    draft_skill_body,
    load_clusters_from_ab_results,
    load_failure_clusters,
    _domain_to_skill_name,
    _auto_description,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_task(tasks_dir: Path, task_id: str, domain: str, instruction: str) -> None:
    d = tasks_dir / task_id
    d.mkdir(parents=True)
    (d / "task.toml").write_text(
        f'[task]\nid = "{task_id}"\ndomain = "{domain}"\nskill = "test-skill"\n'
    )
    (d / "instruction.md").write_text(instruction)


def _make_db(db_path: Path, runs: list[dict]) -> None:
    con = sqlite3.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY, task_id TEXT, skill_name TEXT,
        condition TEXT, score REAL, passed INTEGER, failure_mode TEXT, langsmith_url TEXT
    )""")
    for r in runs:
        con.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
            (r["run_id"], r["task_id"], r.get("skill_name"), r["condition"],
             r["score"], int(r["passed"]), r.get("failure_mode"), None),
        )
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_domain_to_skill_name_known():
    assert _domain_to_skill_name("hotel_search") == "hotel-search"
    assert _domain_to_skill_name("booking_flow") == "booking-skill"
    assert _domain_to_skill_name("fare_rules") == "fare-rules"


def test_domain_to_skill_name_unknown():
    assert _domain_to_skill_name("disruption") == "disruption-handling"
    assert _domain_to_skill_name("baggage_policy") == "baggage-policy"


def test_build_frontmatter_structure():
    fm = build_frontmatter("disruption-handling", "Handle disruptions.")
    assert "name: disruption-handling" in fm
    assert "description: Handle disruptions." in fm
    assert "license: Apache-2.0" in fm
    assert fm.startswith("---\n")
    assert fm.endswith("---\n")


def test_auto_description_contains_domain():
    desc = _auto_description("disruption-handling", "disruption")
    assert "disruption" in desc


# ---------------------------------------------------------------------------
# Cluster loading from trajectory.db
# ---------------------------------------------------------------------------

def test_load_failure_clusters_from_db(tmp_path: Path):
    tasks_dir = tmp_path / "tasks"
    for i in range(6):
        _make_task(tasks_dir, f"disruption-00{i}", "disruption", f"My flight was cancelled {i}")

    runs = [
        {"run_id": f"r{i}", "task_id": f"disruption-00{i}", "condition": "no_skill",
         "score": 0.1, "passed": False, "failure_mode": "NO_TOOL_CALL"}
        for i in range(6)
    ]
    db = tmp_path / "trajectory.db"
    _make_db(db, runs)

    clusters = load_failure_clusters(db, tasks_dir, min_failures=5)
    assert len(clusters) == 1
    assert clusters[0].domain == "disruption"
    assert clusters[0].suggested_skill_name == "disruption-handling"
    assert clusters[0].n_failures == 6
    assert clusters[0].failure_mode == "NO_TOOL_CALL"


def test_load_failure_clusters_skips_existing(tmp_path: Path):
    tasks_dir = tmp_path / "tasks"
    for i in range(6):
        _make_task(tasks_dir, f"hotel-00{i}", "hotel_search", f"Find hotels in Paris {i}")

    runs = [
        {"run_id": f"r{i}", "task_id": f"hotel-00{i}", "condition": "no_skill",
         "score": 0.1, "passed": False, "failure_mode": "WRONG_TOOL"}
        for i in range(6)
    ]
    db = tmp_path / "trajectory.db"
    _make_db(db, runs)

    # hotel-search already exists → should be skipped
    clusters = load_failure_clusters(db, tasks_dir, min_failures=5,
                                     existing_skills={"hotel-search"})
    assert clusters == []


def test_load_failure_clusters_below_threshold(tmp_path: Path):
    tasks_dir = tmp_path / "tasks"
    for i in range(3):
        _make_task(tasks_dir, f"disruption-00{i}", "disruption", f"Cancelled {i}")

    runs = [
        {"run_id": f"r{i}", "task_id": f"disruption-00{i}", "condition": "no_skill",
         "score": 0.0, "passed": False, "failure_mode": "NO_TOOL_CALL"}
        for i in range(3)
    ]
    db = tmp_path / "trajectory.db"
    _make_db(db, runs)

    clusters = load_failure_clusters(db, tasks_dir, min_failures=5)
    assert clusters == []


# ---------------------------------------------------------------------------
# Cluster loading from ab_results.json
# ---------------------------------------------------------------------------

def test_load_clusters_from_ab_results(tmp_path: Path):
    tasks_dir = tmp_path / "tasks"
    for i in range(4):
        _make_task(tasks_dir, f"disruption-00{i}", "disruption", f"Rebooking task {i}")

    tasks_payload = [
        {"no_skill": {"task_id": f"disruption-00{i}", "domain": "disruption", "score": 0.1}}
        for i in range(4)
    ]
    ab_path = tmp_path / "ab_results.json"
    ab_path.write_text(json.dumps({"tasks": tasks_payload}))

    clusters = load_clusters_from_ab_results(ab_path, tasks_dir, min_failures=3)
    assert len(clusters) == 1
    assert clusters[0].domain == "disruption"
    assert clusters[0].n_failures == 4


# ---------------------------------------------------------------------------
# LLM draft
# ---------------------------------------------------------------------------

def test_draft_skill_body_calls_llm():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="# Disruption\n\n## Workflow\n\n1. Step one.\n"))]
    )
    cluster = FailureCluster(
        domain="disruption",
        failure_mode="NO_TOOL_CALL",
        task_ids=["t1", "t2"],
        instructions=["Flight cancelled", "Need rebooking"],
        suggested_skill_name="disruption-handling",
        description="Handle disruptions.",
    )
    result = draft_skill_body(cluster, mock_client)
    assert "## Workflow" in result
    mock_client.chat.completions.create.assert_called_once()


def test_draft_skill_body_includes_domain_in_prompt():
    captured = {}

    def fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return MagicMock(choices=[MagicMock(message=MagicMock(content="# Body"))])

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = fake_create

    cluster = FailureCluster(
        domain="disruption",
        failure_mode="MISSING_PARAM",
        task_ids=["t1"],
        instructions=["Rebook my flight"],
        suggested_skill_name="disruption-handling",
        description="Handle flight disruptions.",
    )
    draft_skill_body(cluster, mock_client)
    prompt = captured["messages"][0]["content"]
    assert "disruption" in prompt
    assert "disruption-handling" in prompt
    assert "MISSING_PARAM" in prompt
