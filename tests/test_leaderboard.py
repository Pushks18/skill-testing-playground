# tests/test_leaderboard.py
"""Tests for eval/leaderboard.py — per-model aggregation + backward compat."""
from __future__ import annotations
import json
import pathlib
import tempfile

import pytest

from eval.leaderboard import collect_results, summarize_skill, summarize_by_model


# ---------------------------------------------------------------------------
# Fixtures — synthetic result dicts
# ---------------------------------------------------------------------------

def _task(skill_name, task_id, delta, model=None, task_weight=1.0):
    """Build a minimal per-task result dict as written by _build_summary tasks[]."""
    d = {
        "skill_name": skill_name,
        "task_id": task_id,
        "delta": delta,
        "task_weight": task_weight,
    }
    if model is not None:
        d["model"] = model
    return d


# Two models running the same skill
GEMINI_TASK_1 = _task("flight-search", "fs-001", delta=0.20, model="google/gemini-2.5-flash")
GEMINI_TASK_2 = _task("flight-search", "fs-002", delta=0.10, model="google/gemini-2.5-flash")
GPT_TASK_1    = _task("flight-search", "fs-001", delta=-0.05, model="gpt-4o-mini")
GPT_TASK_2    = _task("flight-search", "fs-002", delta=0.30, model="gpt-4o-mini")

# Legacy result — no 'model' key at all
LEGACY_TASK   = _task("booking-skill", "bk-001", delta=0.15)  # no model key


# ---------------------------------------------------------------------------
# summarize_skill — basic single-model behaviour
# ---------------------------------------------------------------------------

class TestSummarizeSkillBasic:
    def test_returns_skill_name(self):
        s = summarize_skill("flight-search", [GEMINI_TASK_1])
        assert s["skill"] == "flight-search"

    def test_weighted_delta_single_task(self):
        s = summarize_skill("flight-search", [GEMINI_TASK_1])
        assert s["weighted_delta"] == pytest.approx(0.20, abs=1e-3)

    def test_n_tasks(self):
        s = summarize_skill("flight-search", [GEMINI_TASK_1, GEMINI_TASK_2])
        assert s["n_tasks"] == 2

    def test_regression_rate_zero(self):
        s = summarize_skill("flight-search", [GEMINI_TASK_1, GEMINI_TASK_2])
        assert s["regression_rate"] == 0.0

    def test_regression_rate_nonzero(self):
        s = summarize_skill("flight-search", [GEMINI_TASK_1, GPT_TASK_1])
        # GPT_TASK_1 has delta=-0.05 → regression
        assert s["regression_rate"] == pytest.approx(0.5, abs=1e-3)

    def test_model_all_when_no_filter(self):
        s = summarize_skill("flight-search", [GEMINI_TASK_1, GPT_TASK_1])
        assert s["model"] == "all"

    def test_empty_results_returns_empty(self):
        assert summarize_skill("flight-search", []) == {}


# ---------------------------------------------------------------------------
# summarize_skill — model-filtered behaviour (Phase 5 new feature)
# ---------------------------------------------------------------------------

class TestSummarizeSkillByModel:
    def test_filter_gemini_only(self):
        all_tasks = [GEMINI_TASK_1, GEMINI_TASK_2, GPT_TASK_1, GPT_TASK_2]
        s = summarize_skill("flight-search", all_tasks, model="google/gemini-2.5-flash")
        assert s["n_tasks"] == 2
        assert s["weighted_delta"] == pytest.approx((0.20 + 0.10) / 2, abs=1e-3)
        assert s["model"] == "google/gemini-2.5-flash"

    def test_filter_gpt_only(self):
        all_tasks = [GEMINI_TASK_1, GEMINI_TASK_2, GPT_TASK_1, GPT_TASK_2]
        s = summarize_skill("flight-search", all_tasks, model="gpt-4o-mini")
        assert s["n_tasks"] == 2
        assert s["model"] == "gpt-4o-mini"

    def test_filter_nonexistent_model_empty(self):
        s = summarize_skill("flight-search", [GEMINI_TASK_1], model="claude-opus")
        assert s == {}

    def test_regression_rate_model_filtered(self):
        all_tasks = [GEMINI_TASK_1, GPT_TASK_1]
        # gemini has delta=+0.20 → no regression
        s = summarize_skill("flight-search", all_tasks, model="google/gemini-2.5-flash")
        assert s["regression_rate"] == 0.0
        # gpt has delta=-0.05 → regression
        s2 = summarize_skill("flight-search", all_tasks, model="gpt-4o-mini")
        assert s2["regression_rate"] == 1.0


# ---------------------------------------------------------------------------
# summarize_by_model — per-model rows
# ---------------------------------------------------------------------------

class TestSummarizeByModel:
    def test_two_models_produce_two_rows(self):
        all_tasks = [GEMINI_TASK_1, GEMINI_TASK_2, GPT_TASK_1, GPT_TASK_2]
        rows = summarize_by_model("flight-search", all_tasks)
        assert len(rows) == 2

    def test_rows_have_model_field(self):
        all_tasks = [GEMINI_TASK_1, GPT_TASK_1]
        rows = summarize_by_model("flight-search", all_tasks)
        models = {r["model"] for r in rows}
        assert "google/gemini-2.5-flash" in models
        assert "gpt-4o-mini" in models

    def test_single_model_one_row(self):
        rows = summarize_by_model("flight-search", [GEMINI_TASK_1, GEMINI_TASK_2])
        assert len(rows) == 1
        assert rows[0]["model"] == "google/gemini-2.5-flash"

    def test_empty_input_empty_output(self):
        rows = summarize_by_model("flight-search", [])
        assert rows == []


# ---------------------------------------------------------------------------
# Legacy backward compatibility — tasks without 'model' key → "unknown"
# ---------------------------------------------------------------------------

class TestLegacyBackwardCompat:
    def test_legacy_task_defaults_model_unknown(self):
        """Tasks without a 'model' key must be grouped under 'unknown'."""
        rows = summarize_by_model("booking-skill", [LEGACY_TASK])
        assert len(rows) == 1
        assert rows[0]["model"] == "unknown"

    def test_summarize_skill_includes_legacy_task_in_all(self):
        s = summarize_skill("booking-skill", [LEGACY_TASK])
        assert s["n_tasks"] == 1
        assert s["model"] == "all"

    def test_summarize_skill_filter_unknown_finds_legacy(self):
        s = summarize_skill("booking-skill", [LEGACY_TASK], model="unknown")
        assert s["n_tasks"] == 1
        assert s["model"] == "unknown"

    def test_mixed_legacy_and_new_tasks(self):
        """Legacy tasks appear under 'unknown'; new tasks under their model."""
        mixed = [LEGACY_TASK, _task("booking-skill", "bk-002", delta=0.30, model="gpt-4o-mini")]
        rows = summarize_by_model("booking-skill", mixed)
        models = {r["model"] for r in rows}
        assert "unknown" in models
        assert "gpt-4o-mini" in models


# ---------------------------------------------------------------------------
# collect_results — reads new-format (dict) result files
# ---------------------------------------------------------------------------

class TestCollectResults:
    def _write_new_format(self, tmp_dir, skill_name, model, tasks):
        path = pathlib.Path(tmp_dir) / f"{skill_name}_ab_results.json"
        payload = {
            "skill_name": skill_name,
            "model": model,
            "weighted_delta": 0.1,
            "regression_rate": 0.0,
            "verdict": "PASS",
            "tier": 0,
            "flagged_tasks": [],
            "regression_traces": {},
            "cost": {},
            "tasks": tasks,
        }
        path.write_text(json.dumps(payload))
        return path

    def _write_old_format(self, tmp_dir, tasks):
        """Old format: plain list of task dicts (no skill-level wrapper)."""
        path = pathlib.Path(tmp_dir) / "legacy_ab_results.json"
        path.write_text(json.dumps(tasks))
        return path

    def test_new_format_model_propagated(self, tmp_path):
        self._write_new_format(
            tmp_path, "flight-search", "gpt-4o-mini",
            [{"skill_name": "flight-search", "task_id": "fs-001", "delta": 0.1, "task_weight": 1.0}],
        )
        by_skill = collect_results(tmp_path)
        assert "flight-search" in by_skill
        assert by_skill["flight-search"][0]["model"] == "gpt-4o-mini"

    def test_old_format_model_defaults_unknown(self, tmp_path):
        legacy_task = {"skill_name": "booking-skill", "task_id": "bk-001", "delta": 0.2, "task_weight": 1.0}
        self._write_old_format(tmp_path, [legacy_task])
        by_skill = collect_results(tmp_path)
        assert "booking-skill" in by_skill
        assert by_skill["booking-skill"][0]["model"] == "unknown"

    def test_two_model_files_same_skill(self, tmp_path):
        self._write_new_format(
            tmp_path, "flight-search", "google/gemini-2.5-flash",
            [{"skill_name": "flight-search", "task_id": "fs-001", "delta": 0.2, "task_weight": 1.0}],
        )
        gpt_path = pathlib.Path(tmp_path) / "flight-search_gpt_ab_results.json"
        gpt_path.write_text(json.dumps({
            "skill_name": "flight-search",
            "model": "gpt-4o-mini",
            "tasks": [{"skill_name": "flight-search", "task_id": "fs-001", "delta": -0.05, "task_weight": 1.0}],
        }))
        by_skill = collect_results(tmp_path)
        assert len(by_skill["flight-search"]) == 2
        models = {r["model"] for r in by_skill["flight-search"]}
        assert models == {"google/gemini-2.5-flash", "gpt-4o-mini"}

    def test_corrupt_file_skipped(self, tmp_path):
        (pathlib.Path(tmp_path) / "bad_ab_results.json").write_text("NOT JSON{{{")
        by_skill = collect_results(tmp_path)
        assert by_skill == {}
