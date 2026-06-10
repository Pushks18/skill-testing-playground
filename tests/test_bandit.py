# tests/test_bandit.py
"""Tests for eval/optimizer/bandit.py — deterministic via seeded random."""
from __future__ import annotations

import json
import pathlib

import pytest

from eval.optimizer.bandit import BanditState, STRATEGIES, DEFAULT_BANDIT_PATH


LAYER = "harness:base_prompt"
LAYER2 = "skill:content"


# ── cold arms explore deterministically ─────────────────────────────────────

def test_cold_arms_select_returns_valid_strategy():
    """With all arms at Beta(1,1), any STRATEGIES member is valid."""
    state = BanditState()
    strategy = state.select_strategy(LAYER, STRATEGIES, seed=42)
    assert strategy in STRATEGIES


def test_cold_arms_deterministic_with_seed():
    """Same seed produces same selection."""
    s1 = BanditState()
    s2 = BanditState()
    assert s1.select_strategy(LAYER, STRATEGIES, seed=99) == s2.select_strategy(LAYER, STRATEGIES, seed=99)


def test_cold_arms_different_seeds_may_differ():
    """Different seeds can produce different selections (not guaranteed but very likely)."""
    state = BanditState()
    results = {state.select_strategy(LAYER, STRATEGIES, seed=i) for i in range(20)}
    # With 5 arms and 20 seeds we expect at least 2 distinct results
    assert len(results) >= 2


# ── after updates, heavily rewarded arm is preferred ────────────────────────

def test_update_reward_raises_alpha():
    state = BanditState()
    arm = "push-tool-action"
    for _ in range(5):
        state.update(LAYER, arm, reward=True)
    key = f"{LAYER}|{arm}"
    alpha, beta = state.arms[key]
    assert alpha == 6.0  # prior 1 + 5 successes
    assert beta == 1.0


def test_update_failure_raises_beta():
    state = BanditState()
    arm = "simplify"
    for _ in range(3):
        state.update(LAYER, arm, reward=False)
    key = f"{LAYER}|{arm}"
    alpha, beta = state.arms[key]
    assert alpha == 1.0
    assert beta == 4.0  # prior 1 + 3 failures


def test_selection_prefers_heavily_rewarded_arm():
    """After 10 successes on one arm, Thompson sampling should pick it most often."""
    winner = "push-tool-action"
    state = BanditState()
    for _ in range(10):
        state.update(LAYER, winner, reward=True)

    # With alpha=11 vs beta=1, the winner should dominate across many seeds.
    # The mean of the winner's Beta(11,1) is 11/12 ≈ 0.917; other arms are Beta(1,1)
    # with mean 0.5. Over 100 seeds expect well above 50%.
    picks = [state.select_strategy(LAYER, STRATEGIES, seed=i) for i in range(100)]
    assert picks.count(winner) > 50, (
        f"Expected majority for {winner!r}, got {picks.count(winner)}/100"
    )


def test_repeated_failures_depress_arm_selection():
    """Crash-style updates (reward=False, as recorded for crashed/timed-out
    clusters) must make the arm unlikely to be picked again."""
    loser = "push-tool-action"
    state = BanditState()
    for _ in range(10):
        state.update(LAYER, loser, reward=False)

    # Beta(1,11) mean ≈ 0.083 vs Beta(1,1) mean 0.5 for the other four arms.
    picks = [state.select_strategy(LAYER, STRATEGIES, seed=i) for i in range(100)]
    assert picks.count(loser) < 20, (
        f"Expected crash-penalized arm to be rare, got {picks.count(loser)}/100"
    )


# ── save/load roundtrip ──────────────────────────────────────────────────────

def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "bandit_state.json"
    state = BanditState()
    state.update(LAYER, "broaden-coverage", reward=True)
    state.update(LAYER, "simplify", reward=False)
    state.save(path)

    loaded = BanditState.load(path)
    key_bc = f"{LAYER}|broaden-coverage"
    key_si = f"{LAYER}|simplify"
    assert loaded.arms[key_bc] == [2.0, 1.0]
    assert loaded.arms[key_si] == [1.0, 2.0]


def test_load_missing_file_returns_empty_state(tmp_path):
    path = tmp_path / "nonexistent_bandit.json"
    state = BanditState.load(path)
    assert state.arms == {}


def test_load_corrupt_file_returns_empty_state(tmp_path):
    path = tmp_path / "bandit_state.json"
    path.write_text("not-valid-json")
    state = BanditState.load(path)
    assert state.arms == {}


def test_save_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "dir" / "bandit_state.json"
    state = BanditState()
    state.update(LAYER, "add-edge-case", reward=True)
    state.save(path)
    assert path.exists()
    loaded = BanditState.load(path)
    key = f"{LAYER}|add-edge-case"
    assert loaded.arms[key] == [2.0, 1.0]


def test_save_load_json_schema(tmp_path):
    """The saved JSON has an 'arms' key at the top level."""
    path = tmp_path / "bandit_state.json"
    state = BanditState()
    state.update(LAYER, "tighten-specificity", reward=True)
    state.save(path)
    data = json.loads(path.read_text())
    assert "arms" in data
    assert isinstance(data["arms"], dict)


# ── update on unseen arm initializes ────────────────────────────────────────

def test_update_unseen_arm_initializes():
    state = BanditState()
    assert f"{LAYER}|push-tool-action" not in state.arms
    state.update(LAYER, "push-tool-action", reward=True)
    key = f"{LAYER}|push-tool-action"
    assert key in state.arms
    assert state.arms[key] == [2.0, 1.0]  # prior 1 + 1 success


def test_update_new_layer_arm_initializes():
    """Updating an arm on a layer never seen before should work."""
    state = BanditState()
    state.update("skill:edge-case-layer", "simplify", reward=False)
    key = "skill:edge-case-layer|simplify"
    assert state.arms[key] == [1.0, 2.0]


# ── posterior table ──────────────────────────────────────────────────────────

def test_posterior_table_empty():
    state = BanditState()
    assert state.posterior_table() == []


def test_posterior_table_fields():
    state = BanditState()
    state.update(LAYER, "push-tool-action", reward=True)
    state.update(LAYER, "simplify", reward=False)
    rows = state.posterior_table()
    assert len(rows) == 2
    for row in rows:
        assert "arm" in row
        assert "mean" in row
        assert "n" in row
        assert 0.0 <= row["mean"] <= 1.0
        assert row["n"] >= 0


def test_posterior_table_mean_formula():
    state = BanditState()
    state.update(LAYER, "add-edge-case", reward=True)
    state.update(LAYER, "add-edge-case", reward=True)
    # alpha=3, beta=1 → mean = 3/(3+1) = 0.75, n = 3+1-2 = 2
    rows = {r["arm"]: r for r in state.posterior_table()}
    row = rows[f"{LAYER}|add-edge-case"]
    assert row["mean"] == pytest.approx(0.75, abs=0.001)
    assert row["n"] == 2


# ── STRATEGIES constant ──────────────────────────────────────────────────────

def test_strategies_list_contents():
    expected = {"push-tool-action", "broaden-coverage", "tighten-specificity",
                "add-edge-case", "simplify"}
    assert set(STRATEGIES) == expected


def test_strategies_list_length():
    assert len(STRATEGIES) == 5


# ── multi-layer isolation ────────────────────────────────────────────────────

def test_updates_isolated_by_layer():
    """Updates on one layer must not affect another layer's arms."""
    state = BanditState()
    for _ in range(5):
        state.update(LAYER, "push-tool-action", reward=True)
    # LAYER2 arm should be at prior if we've never updated it
    state._ensure_arm(LAYER2, "push-tool-action")
    key2 = f"{LAYER2}|push-tool-action"
    assert state.arms[key2] == [1.0, 1.0]
