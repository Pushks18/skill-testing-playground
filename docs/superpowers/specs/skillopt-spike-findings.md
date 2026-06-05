# SkillOpt 0.1.0 spike findings (Task 2)

Spike run: 2026-06-05. Test: `tests/test_skillopt_spike.py::test_trainer_end_to_end_with_stub`.
Completed 1 epoch in ~0.1 s, zero LLM calls, zero API cost.

---

## 1. skill_init semantics: text literal or file path?

**Answer: file path only.**

`trainer.py` line 689–695:
```python
skill_init_path = os.path.abspath(cfg["skill_init"])
if os.path.exists(skill_init_path):
    with open(skill_init_path) as f:
        skill_init = f.read()
    print(f"  [initial skill] {skill_init_path} ({len(skill_init)} chars)")
else:
    skill_init = ""
    print("  [initial skill] no initial skill file — starting from blank")
```

`cfg["skill_init"]` is always passed through `os.path.abspath`. If the path does not
exist, the trainer silently falls back to an empty string `""`. A text literal
(e.g., `"Initial skill text..."`) is treated as a relative path, resolved to an
absolute path that does not exist, and the skill starts blank.

**Evidence from spike run output:**
```
  [initial skill] /tmp/.../initial_skill.md (40 chars)
```
File contained `"Initial skill text. Step 1: do the task."`.

---

## 2. train() return value: type and keys

**Answer: `dict` with the following top-level keys (verbatim from spike):**

```python
{
    "version": "skillopt-0.1.0",
    "config": { ... },                    # redacted copy of flat cfg at runtime
    "baseline_selection_hard": 0.0,       # gate score of skill_init on val split
    "best_selection_hard": 0.95,          # best gate score achieved
    "best_step": 1,                       # global step where best was recorded
    "current_origin": "step_0001",
    "best_origin": "step_0001",
    "total_steps": 1,                     # len(history)
    "total_accepts": 1,
    "total_rejects": 0,
    "total_skips": 0,
    "epoch_stats": [
        {
            "epoch": 1,
            "steps": [1],
            "accepts": 1,
            "rejects": 0,
            "skips": 0,
            "best_score_at_epoch_end": 0.95,
            "current_score_at_epoch_end": 0.95
        }
    ],
    "baseline_test_hard": None,           # None when eval_test=False
    "baseline_test_soft": None,
    "test_hard": None,
    "test_soft": None,
    "test_delta_hard": None,
    "total_wall_time_s": 0.0,
    "token_summary": {
        "_total": {"calls": 0, "prompt_tokens": 0,
                   "completion_tokens": 0, "total_tokens": 0}
    }
}
```

`gate_metric="mixed"`, `gate_mixed_weight=0.5` → gate score = 0.5*hard + 0.5*soft.
Baseline (no IMPROVED): hard=0.0, soft=0.2 → mixed=0.10.
After patch (IMPROVED): hard=1.0, soft=0.9 → mixed=0.95.

---

## 3. Best-artifact location: exact relative path under out_root

**Answer: `out_root/best_skill.md` (single file, overwritten in place at each accept).**

Also versioned copies at `out_root/skills/skill_v{step:04d}.md`:
- `skills/skill_v0000.md` — initial skill (written before training loop)
- `skills/skill_v0001.md` — skill after step 1 (current skill at end of step)

`history.json` does NOT embed the skill text; it records `best_step` (int) and
`best_score` (float) per record. To recover the best skill from history, read
`best_skill.md` (always current) or `skills/skill_v{best_step:04d}.md`.

**Full out_root tree from spike:**
```
_generated_splits/travel-stub_5-3-2_seed7/split_manifest.json
_generated_splits/travel-stub_5-3-2_seed7/test/items.json
_generated_splits/travel-stub_5-3-2_seed7/train/items.json
_generated_splits/travel-stub_5-3-2_seed7/val/items.json
best_skill.md                     ← THE best artifact
config.json
history.json
runtime_state.json
skills/skill_v0000.md
skills/skill_v0001.md
steps/step_0001/candidate_skill.md
steps/step_0001/edit_apply_report.json
steps/step_0001/merged_patch.json
steps/step_0001/ranked_edits.json
steps/step_0001/step_record.json
steps/step_0001/trajectory_digest.json
summary.json
```

---

## 4. Final test-split evaluation: trainer or driver?

**Answer: the trainer runs it internally when `cfg["eval_test"] = True`.**

At the end of `train()` (after all epochs), if `cfg["eval_test"]` is `True`, the
trainer calls `_build_eval_env(split="valid_unseen", ...)` (which maps to the
`"test"` split via `_SPLIT_ALIAS`) and runs two rollouts: one with `skill_init`
(baseline) and one with `best_skill`. Results are written to
`out_root/test_eval/summary.json` and `out_root/test_eval_baseline/summary.json`.

With `eval_test=False` (used in this spike to save time), `train()` returns
`test_hard=None`, `test_soft=None`, `test_delta_hard=None`.

**The driver does NOT need to call any separate evaluation function after
`train()`.** Setting `eval_test=True` is sufficient.

---

## 5. RawPatch dict shape accepted by reflect → aggregate

**Answer: two equivalent shapes are accepted.**

**Shape A (wrapped, canonical `RawPatch`):**
```python
{
    "patch": {
        "edits": [{"op": "append", "content": "..."}],
        "reasoning": "optional"
    },
    "source_type": "failure",   # or "success"
    "batch_size": 0             # optional
}
```

**Shape B (unwrapped, flat patch dict) — used in this spike:**
```python
{
    "edits": [{"op": "append", "content": "..."}],
    "summary": "stub patch"     # any extra keys are ignored
}
```

`_normalise_patches` does `inner = p.get("patch", p)` — if there is no `"patch"`
key, it uses the dict itself as the inner patch. `get_payload_items(inner, "patch")`
then looks for the `"edits"` key. Both shapes work.

**Edit dict keys (for `op="append"`):**
- `"op"`: one of `"append"`, `"insert_after"`, `"replace"`, `"delete"`
- `"content"`: text to insert/append/replace with (required for add ops)
- `"target"`: text to search for (required for `insert_after`, `replace`, `delete`)

**Source type inference:** if `source_type` is absent, the patch is treated as
`"failure"` (the `_normalise_patches` default).

---

## 6. LLM dependence of aggregate/select stages with a 1-patch reflect

**Answer: aggregate and select bypass the LLM entirely when conditions are met.**

**Aggregate (stage 3):** `merge_patches` calls `load_prompt(...)` unconditionally
before `_hierarchical_merge`. In this stripped venv installation the `.md` prompt
files are absent and `load_prompt` raises `FileNotFoundError`. This required one
monkeypatch.

`_hierarchical_merge` skips the LLM when `len(patches) == 1` (returns the single
patch directly). So with exactly 1 failure patch and 0 success patches: the
failure-side `_hierarchical_merge` returns immediately, the success side returns
an empty dict, and `merge_patches` returns `failure_merged` with no LLM call.
But `load_prompt` is still called for prompt loading at the top of `merge_patches`.

**Select (stage 4):** `rank_and_select` checks `if len(edits) <= max_edits: return patch`
before any LLM call. With 1 edit and `edit_budget=3`, no LLM is invoked.

**Monkeypatches applied (narrowest possible):**
```python
import skillopt.prompts
import skillopt.gradient.aggregate
import skillopt.optimizer.clip

monkeypatch.setattr(skillopt.prompts, "load_prompt", _stub_load_prompt)
monkeypatch.setattr(skillopt.gradient.aggregate, "load_prompt", _stub_load_prompt)
monkeypatch.setattr(skillopt.optimizer.clip, "load_prompt", _stub_load_prompt)
```

Where `_stub_load_prompt(name, env=None) -> str` returns `f"stub prompt: {name}"`.

**Why:** the skillopt 0.1.0 venv distribution ships with no `.md` prompt files in
`skillopt/prompts/`. The `load_prompt` function raises `FileNotFoundError` when
any prompt is requested. Patching at the module-attribute level covers all three
call sites without touching trainer internals.

**Token count after full run: 0 calls, 0 tokens.** No LLM was contacted.

---

## 7. cfg keys actually consumed (working flat cfg from the spike, verbatim)

```python
cfg = {
    # identity
    "env": "travel-stub",
    "out_root": str(out_root),
    "skill_init": str(skill_file),     # must be an absolute path to an existing file

    # model (required by trainer even if no LLM is called)
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

    # optimizer / lr
    "edit_budget": 3,

    # evaluation / gate
    "use_gate": True,
    "gate_metric": "mixed",
    "gate_mixed_weight": 0.5,
    "sel_env_num": 3,
    "test_env_num": 2,
    "eval_test": False,
}
```

Keys set automatically by the trainer at runtime (written back into `cfg` and
persisted to `config.json`):
- `"optimizer_backend"`: `"openai_chat"` (inferred from default `model_backend="azure_openai"`)
- `"target_backend"`: `"openai_chat"`
- `"train_size"`: `5` (inferred from `len(dataloader.train_items)`)
- `"steps_per_epoch"`: `1` (= `ceil(train_size / (batch_size * accumulation))`)
- `"batches_per_epoch"`: `1`
- `"samples_per_epoch"`: `5`
- `"skill_update_mode"`: `"patch"`
- `"lr_control_mode"`: `"fixed"`

---

## 8. Anything surprising

1. **`steps_per_epoch` in cfg is ignored.** The task description says
   `steps_per_epoch` is a flat cfg key, but the trainer computes it from
   `ceil(train_size / (batch_size * accumulation))` and **overwrites** whatever was
   in `cfg`. Passing `"steps_per_epoch": 1` in the config has no effect; it is
   determined entirely by data size and batch parameters.

2. **Baseline eval always runs before the first training step.** Even for 1 epoch,
   the trainer evaluates `skill_init` on the `"valid_seen"` (val) split using
   `sel_env_num` items before entering the epoch loop. This consumes 1 rollout call
   to establish `current_score`. Plan downstream code to expect this prefix rollout.

3. **3 rollout calls for 1 training step:**
   - Call 1: baseline on val split (3 items) — before any training
   - Call 2: train batch rollout (5 items) — stage 1 of step 1
   - Call 3: selection eval (3 items) — stage 6 of step 1 (gate evaluation)
   Total: `1 + steps_per_epoch * (1 + 1) = 3`.

4. **`_generated_splits/` is written inside `out_root`.** When `split_mode="ratio"`,
   the split directory defaults to `{out_root}/_generated_splits/{env}_{ratio}_seed{n}`.
   This is deterministic and the same path is reused on resume.

5. **`use_gate=False` raises `ValueError`** — gate validation is mandatory.
   The config key is checked but the trainer hard-requires the gate to be on.

6. **reflect can return the flat dict without `"patch"` wrapper.** Shape B (§5)
   works with the normalizer's `inner = p.get("patch", p)` fallback. However
   `source_type` is inferred as `"failure"` when absent, which is intentional for
   the spike.

7. **`summary.json` key for best score is `"best_selection_hard"`, not `"best_score"`.
   ** `train()` returns `best_selection_hard` (the gate-metric score on the selection
   set), not a raw hard accuracy. With `gate_metric="mixed"`, this value is
   `0.5*hard + 0.5*soft`, NOT `hard` alone.
