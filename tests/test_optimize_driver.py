# tests/test_optimize_driver.py
import json
import pathlib
import types

import pytest
import yaml

from eval.optimizer.optimize import (
    resolve_target, qualifying_clusters, estimate_rollout_calls, write_proposed,
    _pick_strategy, _pick_seed, _record_archive, refine_harness_key,
)
from eval.optimizer.archive import Archive, _sha256
from eval.optimizer.bandit import BanditState, STRATEGIES


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


# ── _pick_strategy tests ──────────────────────────────────────────────────────

def _make_args(**kwargs):
    """Build a minimal args namespace for _pick_strategy / _pick_seed."""
    defaults = {"strategy": None, "explore": False, "seed": 7, "no_embed": True}
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def test_pick_strategy_override(tmp_path):
    """--strategy override must bypass the bandit."""
    bandit_path = tmp_path / "bandit_state.json"
    cluster = _cluster("harness:base_prompt", "agent/harness_config.yaml::base_system_prompt")
    args = _make_args(strategy="simplify")
    result = _pick_strategy(args, cluster, bandit_path)
    assert result == "simplify"


def test_pick_strategy_bandit_cold(tmp_path):
    """With no bandit file, select_strategy returns a valid STRATEGIES member."""
    bandit_path = tmp_path / "bandit_state.json"
    cluster = _cluster("harness:base_prompt", "agent/harness_config.yaml::base_system_prompt")
    args = _make_args(strategy=None, seed=42)
    result = _pick_strategy(args, cluster, bandit_path)
    assert result in STRATEGIES


def test_pick_strategy_bandit_loaded(tmp_path):
    """Bandit state on disk is used for strategy selection when no override."""
    bandit_path = tmp_path / "bandit_state.json"
    # Heavily reward "simplify" so it dominates
    state = BanditState()
    for _ in range(20):
        state.update("harness:base_prompt", "simplify", reward=True)
    state.save(bandit_path)

    cluster = _cluster("harness:base_prompt", "agent/harness_config.yaml::base_system_prompt")
    args = _make_args(strategy=None, seed=5)
    result = _pick_strategy(args, cluster, bandit_path)
    assert result == "simplify"


# ── _pick_seed tests ──────────────────────────────────────────────────────────

def test_pick_seed_no_explore_returns_live(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    args = _make_args(explore=False, seed=7)
    text, source = _pick_seed(args, archive, "harness:base_system_prompt", "live text")
    assert text == "live text"
    assert source == "live"


def test_pick_seed_explore_empty_archive_returns_live(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    args = _make_args(explore=True, seed=0)
    text, source = _pick_seed(args, archive, "harness:base_system_prompt", "live text")
    assert text == "live text"
    assert source == "live"


# ── _record_archive tests ─────────────────────────────────────────────────────

def test_record_archive_adds_initial_entry(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    _record_archive(
        archive=archive,
        run_tag="run_001",
        target_key_str="harness:base_system_prompt",
        layer="harness:base_prompt",
        strategy="push-tool-action",
        seed_text="initial text",
        baseline_text="initial text",  # same as seed (no archive seed)
        best_text="initial text",      # no improvement → only one unique text
        sel_baseline=0.4,
        sel_best=0.4,
        improved=False,
        no_embed=True,
    )
    entries = archive.entries()
    assert len(entries) == 1
    assert entries[0].artifact_text == "initial text"
    assert entries[0].selection_score == 0.4


def test_record_archive_adds_best_when_different(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    _record_archive(
        archive=archive,
        run_tag="run_002",
        target_key_str="harness:base_system_prompt",
        layer="harness:base_prompt",
        strategy="broaden-coverage",
        seed_text="initial text",
        baseline_text="initial text",
        best_text="improved text",      # different → should be stored
        sel_baseline=0.4,
        sel_best=0.7,
        improved=True,
        no_embed=True,
    )
    entries = archive.entries()
    assert len(entries) == 2
    texts = {e.artifact_text for e in entries}
    assert "initial text" in texts
    assert "improved text" in texts
    # Best entry should be marked accepted
    best = next(e for e in entries if e.artifact_text == "improved text")
    assert best.accepted is True
    assert best.selection_score == 0.7


def test_record_archive_best_parent_hash_matches_seed(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    seed = "seed text"
    best = "best text"
    _record_archive(
        archive=archive,
        run_tag="run_003",
        target_key_str="harness:base_system_prompt",
        layer="harness:base_prompt",
        strategy="simplify",
        seed_text=seed,
        baseline_text=seed,
        best_text=best,
        sel_baseline=0.3,
        sel_best=0.8,
        improved=True,
        no_embed=True,
    )
    entries = {e.artifact_text: e for e in archive.entries()}
    best_entry = entries[best]
    assert best_entry.parent_hash == _sha256(seed)


# ── dry-run must not touch archive/bandit ─────────────────────────────────────

def test_dry_run_does_not_create_archive_or_bandit(tmp_path, monkeypatch):
    """dry-run must exit before any archive/bandit file writes."""
    import eval.optimizer.optimize as opt

    archive_path = tmp_path / "archive.jsonl"
    bandit_path = tmp_path / "bandit_state.json"

    # Patch OUTPUT_ROOT so the dry-run report also goes to tmp_path
    monkeypatch.setattr(opt, "OUTPUT_ROOT", tmp_path)

    # Stub out heavy I/O that run_cluster calls before the dry-run guard
    harness_path = tmp_path / "harness_config.yaml"
    harness_path.write_text(yaml.safe_dump({
        "version": "1.0",
        "base_system_prompt": "You are a helpful travel assistant.",
        "tool_descriptions": {},
        "node_prompts": {},
        "optimizable": ["base_system_prompt"],
    }))
    tasks = tmp_path / "tasks"
    tasks.mkdir()

    skill_dir = tmp_path / "ancillery-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: ancillery-skill\n---\n\n# Body\n")

    # Stub initial_artifact and load_raw_items
    monkeypatch.setattr(opt, "initial_artifact", lambda spec: "stub artifact text")

    class _StubAdapter:
        class dataloader:
            @staticmethod
            def load_raw_items(path):
                return [{"id": f"t{i}", "question": "q", "task_type": "ancillery",
                         "task_path": f"/tmp/t{i}"} for i in range(5)]

    original_TravelEnvAdapter = opt.TravelEnvAdapter
    monkeypatch.setattr(opt, "TravelEnvAdapter", lambda **kw: _StubAdapter())

    import skillopt.config as sc
    monkeypatch.setattr(sc, "load_config", lambda path: {})
    monkeypatch.setattr(sc, "flatten_config", lambda cfg: {"num_epochs": 2})

    cluster = _cluster("harness:base_prompt", "agent/harness_config.yaml::base_system_prompt", n=1)
    args = types.SimpleNamespace(
        harness_config=str(harness_path),
        skills_root=str(tmp_path),
        tasks_dir=str(tasks),
        mock_mcp_url="http://localhost:8000",
        seed=7,
        dry_run=True,
        strategy=None,
        explore=False,
        no_embed=True,
        config="eval/optimizer/skillopt_config.yaml",
    )

    report = opt.run_cluster(cluster, args)

    assert report.get("dry_run") is True
    assert "strategy" in report
    assert not archive_path.exists(), "archive.jsonl must not be created on dry-run"
    assert not bandit_path.exists(), "bandit_state.json must not be created on dry-run"


# ── dict-valued harness keys narrow to one sub-key (safe plain-text target) ──

_CONFIG_WITH_TOOLS = {
    "base_system_prompt": "You are helpful.",
    "tool_descriptions": {"validate_passenger": "Validate a passenger.",
                          "modify_booking": "Modify a booking."},
    "node_prompts": {},
}


def test_refine_harness_key_picks_tool_from_evidence():
    cluster = {"task_ids": ["booking-flow-109"], "domain": "booking_flow"}
    classifications = [{"task_id": "booking-flow-109",
                        "evidence": {"first_tool_name": "validate_passenger"}}]
    key = refine_harness_key("tool_descriptions", cluster, classifications, _CONFIG_WITH_TOOLS)
    assert key == "tool_descriptions.validate_passenger"


def test_refine_harness_key_falls_back_without_evidence():
    cluster = {"task_ids": ["x"], "domain": "booking_flow"}
    # no matching classification → cannot resolve a sub-key → unchanged
    assert refine_harness_key("tool_descriptions", cluster, [], _CONFIG_WITH_TOOLS) == "tool_descriptions"
    # empty dict (node_prompts) → unchanged
    assert refine_harness_key("node_prompts", cluster, [], _CONFIG_WITH_TOOLS) == "node_prompts"
    # scalar key → unchanged
    assert refine_harness_key("base_system_prompt", cluster, [], _CONFIG_WITH_TOOLS) == "base_system_prompt"


def test_write_proposed_harness_dotted_subkey(tmp_path):
    base_path = tmp_path / "harness_config.yaml"
    base_path.write_text(yaml.safe_dump(_CONFIG_WITH_TOOLS))
    out = write_proposed(kind="harness", key="tool_descriptions.validate_passenger",
                         artifact_text="Validate the passenger BEFORE booking. Use first.",
                         out_dir=tmp_path, harness_config_path=base_path, skill_path=None)
    proposed = yaml.safe_load(out.read_text())
    assert proposed["tool_descriptions"]["validate_passenger"].startswith("Validate the passenger BEFORE")
    # sibling description preserved; real config untouched
    assert proposed["tool_descriptions"]["modify_booking"] == "Modify a booking."
    assert yaml.safe_load(base_path.read_text())["tool_descriptions"]["validate_passenger"] == "Validate a passenger."


# ── _run_with_timeout watchdog ───────────────────────────────────────────────

def test_run_with_timeout_passthrough():
    from eval.optimizer.optimize import _run_with_timeout
    assert _run_with_timeout(lambda: 42, None) == 42
    assert _run_with_timeout(lambda: 42, 0) == 42


def test_run_with_timeout_returns_within_budget():
    from eval.optimizer.optimize import _run_with_timeout
    assert _run_with_timeout(lambda: "ok", 5) == "ok"


def test_run_with_timeout_raises_on_hang():
    import time
    from eval.optimizer.optimize import _run_with_timeout
    with pytest.raises(TimeoutError):
        _run_with_timeout(lambda: time.sleep(3), 1)


def test_run_with_timeout_restores_alarm_state():
    import signal
    from eval.optimizer.optimize import _run_with_timeout
    _run_with_timeout(lambda: None, 5)
    assert signal.alarm(0) == 0  # no alarm left pending


# ── bandit learns from crashes (improvement A) ───────────────────────────────

def _setup_run_cluster_stubs(tmp_path, monkeypatch):
    """Shared stubbing for full run_cluster tests (no real I/O, no skillopt)."""
    import sys as _sys
    import eval.optimizer.optimize as opt

    monkeypatch.setattr(opt, "OUTPUT_ROOT", tmp_path)

    harness_path = tmp_path / "harness_config.yaml"
    harness_path.write_text(yaml.safe_dump({
        "version": "1.0",
        "base_system_prompt": "You are a helpful travel assistant.",
        "tool_descriptions": {},
        "node_prompts": {},
        "optimizable": ["base_system_prompt"],
    }))
    tasks = tmp_path / "tasks"
    tasks.mkdir()

    monkeypatch.setattr(opt, "initial_artifact", lambda spec: "stub artifact text")

    class _StubAdapter:
        class dataloader:
            @staticmethod
            def load_raw_items(path):
                return [{"id": f"t{i}", "question": "q", "task_type": "ancillery",
                         "task_path": f"/tmp/t{i}"} for i in range(5)]

    monkeypatch.setattr(opt, "TravelEnvAdapter", lambda **kw: _StubAdapter())

    import skillopt.config as sc
    monkeypatch.setattr(sc, "load_config", lambda path: {})
    monkeypatch.setattr(sc, "flatten_config", lambda cfg: {"num_epochs": 2})

    # Stub the lazy in-function imports so no real skillopt model/trainer loads.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake_azure = types.ModuleType("skillopt.model.azure_openai")
    fake_azure.configure_azure_openai = lambda **kw: None
    monkeypatch.setitem(_sys.modules, "skillopt.model.azure_openai", fake_azure)

    fake_trainer_mod = types.ModuleType("skillopt.engine.trainer")

    class _FakeTrainer:
        def __init__(self, cfg, adapter):
            pass

        def train(self):
            return {"baseline_selection_hard": 0.4, "best_selection_hard": 0.8,
                    "baseline_test_hard": 0.5, "baseline_test_soft": 0.5,
                    "test_hard": 0.6, "test_soft": 0.6}

    fake_trainer_mod.ReflACTTrainer = _FakeTrainer
    monkeypatch.setitem(_sys.modules, "skillopt.engine.trainer", fake_trainer_mod)

    args = types.SimpleNamespace(
        harness_config=str(harness_path),
        skills_root=str(tmp_path),
        tasks_dir=str(tasks),
        mock_mcp_url="http://localhost:8000",
        seed=7,
        dry_run=False,
        strategy="simplify",   # pin the arm so assertions are deterministic
        explore=False,
        no_embed=True,
        config="eval/optimizer/skillopt_config.yaml",
    )
    cluster = _cluster("harness:base_prompt",
                       "agent/harness_config.yaml::base_system_prompt", n=1)
    return opt, args, cluster


def test_crash_after_strategy_selection_records_one_bandit_failure(tmp_path, monkeypatch):
    """A crash anywhere after the strategy was picked must penalize that arm once."""
    opt, args, cluster = _setup_run_cluster_stubs(tmp_path, monkeypatch)

    def _boom(*a, **kw):
        raise RuntimeError("simulated crash after strategy selection")

    monkeypatch.setattr(opt, "_pick_seed", _boom)

    with pytest.raises(RuntimeError, match="simulated crash"):
        opt.run_cluster(cluster, args)

    state = BanditState.load(tmp_path / "bandit_state.json")
    assert state.arms["harness:base_prompt|simplify"] == [1.0, 2.0]  # one failure


def test_timeout_inside_run_cluster_records_one_bandit_failure(tmp_path, monkeypatch):
    """The --cluster-timeout TimeoutError can fire anywhere in the body and
    must still count against the chosen arm."""
    opt, args, cluster = _setup_run_cluster_stubs(tmp_path, monkeypatch)

    def _hang(*a, **kw):
        raise TimeoutError("cluster run exceeded --cluster-timeout=1s")

    monkeypatch.setattr(opt, "_pick_seed", _hang)

    with pytest.raises(TimeoutError):
        opt.run_cluster(cluster, args)

    state = BanditState.load(tmp_path / "bandit_state.json")
    assert state.arms["harness:base_prompt|simplify"] == [1.0, 2.0]


def test_success_path_updates_bandit_exactly_once(tmp_path, monkeypatch):
    """A completed run must update the arm once (no extra crash penalty)."""
    opt, args, cluster = _setup_run_cluster_stubs(tmp_path, monkeypatch)

    report = opt.run_cluster(cluster, args)

    assert report["improved"] is True
    state = BanditState.load(tmp_path / "bandit_state.json")
    # exactly one success update: alpha 1→2, beta untouched
    assert state.arms["harness:base_prompt|simplify"] == [2.0, 1.0]


def test_crash_before_strategy_selection_leaves_bandit_untouched(tmp_path, monkeypatch):
    """Failures before an arm was picked (e.g. bad target) must not penalize anything."""
    opt, args, cluster = _setup_run_cluster_stubs(tmp_path, monkeypatch)
    cluster["target_artifact"] = "agent/harness_config.yaml::version"  # not whitelisted

    with pytest.raises(ValueError, match="not optimizable"):
        opt.run_cluster(cluster, args)

    assert not (tmp_path / "bandit_state.json").exists()


# ── heartbeat (improvement C) ────────────────────────────────────────────────

def test_heartbeat_emits_while_running_and_stops_cleanly(capsys):
    import time
    from eval.optimizer.optimize import _start_heartbeat

    stop = _start_heartbeat("skills/planning-skill/SKILL.md", 0.05)
    time.sleep(0.3)            # simulate a slow cluster
    stop()
    out = capsys.readouterr().out
    assert "[heartbeat] skills/planning-skill/SKILL.md still running, elapsed" in out

    time.sleep(0.2)            # thread must be stopped: no further beats
    assert "[heartbeat]" not in capsys.readouterr().out


def test_heartbeat_zero_is_noop(capsys):
    import time
    from eval.optimizer.optimize import _start_heartbeat

    stop = _start_heartbeat("anything", 0)
    time.sleep(0.1)
    stop()
    assert capsys.readouterr().out == ""


# ── batch cost cap (improvement D) ───────────────────────────────────────────

def _cap_setup(tmp_path, monkeypatch, n_tasks=10, num_epochs=2):
    """Tasks dir + stubbed skillopt config for _enforce_rollout_cap tests."""
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    for i in range(n_tasks):
        d = tasks / f"planning-{100 + i}"
        d.mkdir()
        (d / "task.toml").write_text('domain = "trip_planning"\n')
        (d / "instruction.md").write_text("Plan the trip.")
    # a non-task dir and a stray file must not be counted
    (tasks / "notes").mkdir()
    (tasks / "README.md").write_text("not a task")

    import skillopt.config as sc
    monkeypatch.setattr(sc, "load_config", lambda path: {})
    monkeypatch.setattr(sc, "flatten_config", lambda cfg: {"num_epochs": num_epochs})
    return tasks


def test_rollout_cap_exceeded_exits_before_spend(tmp_path, monkeypatch):
    from eval.optimizer.optimize import _enforce_rollout_cap

    tasks = _cap_setup(tmp_path, monkeypatch)
    # 10 tasks → split 5/3/2, epochs=2 → 3 + 2*(5+3) + 2*2 = 23 per cluster
    args = types.SimpleNamespace(max_rollout_calls=30, tasks_dir=str(tasks),
                                 config="stub.yaml")
    with pytest.raises(SystemExit) as exc:
        _enforce_rollout_cap(2, args)   # 2 clusters → 46 > 30
    msg = str(exc.value)
    assert "46" in msg and "30" in msg
    assert "max-rollout-calls" in msg


def test_rollout_cap_zero_disables(tmp_path, monkeypatch):
    from eval.optimizer.optimize import _enforce_rollout_cap

    tasks = _cap_setup(tmp_path, monkeypatch)
    args = types.SimpleNamespace(max_rollout_calls=0, tasks_dir=str(tasks),
                                 config="stub.yaml")
    _enforce_rollout_cap(100, args)     # no SystemExit


def test_rollout_cap_under_budget_passes(tmp_path, monkeypatch):
    from eval.optimizer.optimize import _enforce_rollout_cap

    tasks = _cap_setup(tmp_path, monkeypatch)
    args = types.SimpleNamespace(max_rollout_calls=1000, tasks_dir=str(tasks),
                                 config="stub.yaml")
    _enforce_rollout_cap(2, args)       # 46 <= 1000 → no SystemExit


def test_count_tasks_only_counts_complete_task_dirs(tmp_path):
    from eval.optimizer.optimize import _count_tasks

    tasks = tmp_path / "tasks"
    tasks.mkdir()
    good = tasks / "planning-1"
    good.mkdir()
    (good / "task.toml").write_text('domain = "x"\n')
    (good / "instruction.md").write_text("y")
    incomplete = tasks / "planning-2"
    incomplete.mkdir()
    (incomplete / "task.toml").write_text('domain = "x"\n')   # no instruction.md

    assert _count_tasks(tasks) == 1
    assert _count_tasks(tmp_path / "missing") == 0
