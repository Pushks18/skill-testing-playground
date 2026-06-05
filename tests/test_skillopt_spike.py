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
        # Return a dict that _normalise_patches can consume directly:
        # inner = p.get("patch", p) → falls back to the dict itself when no
        # "patch" key is present; get_payload_items then looks for "edits".
        # One bounded edit appending the magic token.
        return [{
            "edits": [{"op": "append", "content": "\nIMPROVED: always call the required tool."}],
            "summary": "stub patch",
        }]

    def get_task_types(self):
        return ["stub"]


def _stub_load_prompt(name: str, env: str | None = None) -> str:
    """Return a trivial stub prompt string so no real prompt files are needed."""
    return f"stub prompt: {name}"


@pytest.mark.slow
def test_trainer_end_to_end_with_stub(tmp_path, monkeypatch):
    # Monkeypatch load_prompt everywhere it is imported so the aggregate/select
    # stages never hit the missing prompt files in this stripped distribution.
    import skillopt.prompts
    import skillopt.gradient.aggregate
    import skillopt.optimizer.clip
    monkeypatch.setattr(skillopt.prompts, "load_prompt", _stub_load_prompt)
    monkeypatch.setattr(skillopt.gradient.aggregate, "load_prompt", _stub_load_prompt)
    monkeypatch.setattr(skillopt.optimizer.clip, "load_prompt", _stub_load_prompt)

    from skillopt.engine.trainer import ReflACTTrainer

    out_root = tmp_path / "spike_out"

    # skill_init must be a file path that EXISTS for the trainer to read it.
    # If the path does not exist, the trainer silently starts from "".
    skill_file = tmp_path / "initial_skill.md"
    skill_file.write_text("Initial skill text. Step 1: do the task.")

    cfg = {
        # flat config (legacy format accepted per skillopt.config docstring)
        "env": "travel-stub",
        "out_root": str(out_root),
        "skill_init": str(skill_file),   # must be a real file path
        # model keys — never actually called because aggregate/select skip LLM
        # when there is exactly 1 patch and edits <= budget
        "optimizer_model": "stub-model",
        "target_model": "stub-model",
        # training
        "num_epochs": 1,
        "batch_size": 5,
        "accumulation": 1,
        "seed": 7,
        # gradient
        "merge_batch_size": 8,
        "analyst_workers": 1,
        # optimizer
        "edit_budget": 3,
        # evaluation / gate
        "use_gate": True,
        "gate_metric": "mixed",
        "gate_mixed_weight": 0.5,
        "sel_env_num": 3,    # how many val items to use for selection eval
        "test_env_num": 2,
        "eval_test": False,  # skip final test split eval in this spike
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

    # result is a dict
    assert isinstance(result, dict), f"expected dict, got {type(result)}"

    # best_skill.md must exist
    best_skill_path = out_root / "best_skill.md"
    assert best_skill_path.exists(), "best_skill.md not written"

    # summary.json and history.json should exist
    assert (out_root / "summary.json").exists(), "summary.json not written"
    assert (out_root / "history.json").exists(), "history.json not written"

    # result keys
    assert "best_selection_hard" in result
    assert "best_step" in result
    assert "version" in result

    # After 1 epoch with a patch that appends IMPROVED, the gate should have
    # accepted the candidate (cand score 0.9*mixed > baseline 0.2*mixed).
    best_skill_content = best_skill_path.read_text()
    print(f"best_skill.md contains IMPROVED: {'IMPROVED' in best_skill_content}")
    print(f"result['best_selection_hard']: {result.get('best_selection_hard')}")
    print(f"result['best_step']: {result.get('best_step')}")
    print(f"result['total_accepts']: {result.get('total_accepts')}")
    print(f"result['total_rejects']: {result.get('total_rejects')}")
    print(f"result['total_skips']: {result.get('total_skips')}")

    # The best skill should contain IMPROVED (gate accepted the patch)
    assert "IMPROVED" in best_skill_content, (
        f"Expected best skill to contain IMPROVED after gate accept, "
        f"got: {best_skill_content[:200]}"
    )
