# SkillOpt Two-Target Optimizer (Slice 3) — Design

**Date:** 2026-06-04
**Status:** Draft for review
**Scope:** Slice 3 of PRD §5.8 — the optimization engine ("the surgeon"). Consumes Slice 1's `failure_classification.json`, edits the artifact Slice 2 made editable. Slice 4 (archive + bandit) remains separate.
**Repo:** `skill-testing-playground`

---

## Decision record

- **Full `EnvAdapter` integration** with the `skillopt` package (user-selected over gate-only). `skillopt==0.1.0` verified on PyPI; APIs below verified against the actual wheel, not the paper.
- **Propose-only**: the optimizer writes `*_proposed.*` files and a report. It never commits, never opens PRs. (PR automation is a possible Slice 3b once proposals prove out.)
- **Mixed gate, never hard**: at ≤10 tasks/domain the hard gate rejects everything (PRD §5.8.3 warning).

## Verified package facts (skillopt 0.1.0, internal name "ReflACT")

- Entry: `ReflACTTrainer(cfg: dict, adapter: EnvAdapter).train()` — programmatic; no need for their CLI registry.
- Adapter contract (called by trainer): `setup(cfg)`, `get_dataloader()`, `build_env_from_batch(batch, out_root)`, `build_train_env(...)`, `build_eval_env(env_num, split, seed)`, `rollout(env, skill_content, out_dir) -> list[dict]`, `reflect(results, skill_content, out_dir) -> raw patches`, `get_task_types()`, `requires_ray() -> False`.
- Rollout result dicts: required `id: str`, `hard: int (0/1)`, `soft: float (0..1)`; useful optional `fail_reason`, `task_type` (see `skillopt.types.RolloutResult`).
- Dataloader: subclass `skillopt.datasets.base.SplitDataLoader`; `split_mode="ratio"` deterministically splits a single item list into train/val/test — exactly our 5/3/2 need.
- Gate: `skillopt.evaluation.gate` — `gate_metric ∈ {hard, soft, mixed}`, `mixed_weight` (default 0.5).
- Model backends: `openai_chat` backend exists (default gpt-4o) — works with our existing `OPENAI_API_KEY` for the optimizer-side LLM stages (reflect/aggregate/select/slow-update). No OpenRouter integration needed inside skillopt.
- The trainer treats the optimized artifact as one text blob ("skill_content") and persists per-step candidates + history under an `out_root`.

---

## Architecture

```
failure_classification.json  (Slice 1 output)
        │
        ▼
eval/optimizer/optimize.py  (driver, NEW)
  per cluster:
    target_kind  = "skill" | "harness"      ← from cluster.layer
    artifact     = SKILL.md body  |  one harness_config key's value
    cfg          = skillopt_config.yaml + per-run overrides
    adapter      = TravelEnvAdapter(target spec)
    ReflACTTrainer(cfg, adapter).train()    ← 6-stage loop, mixed gate
        │ rollout = run_task on split tasks (real eval, mock MCP)
        ▼
  best artifact from out_root
        │
        ▼
  PROPOSED FILES (never committed by the tool):
    harness target → eval/optimizer_output/<run>/harness_config_proposed.yaml
    skill target   → eval/optimizer_output/<run>/SKILL_proposed.md
  + optimization_report.json (baseline / selection / held-out test scores, accepted edits)
```

### New files

| File | Responsibility |
|------|---------------|
| `eval/optimizer/skillopt_adapter.py` | `TravelEnvAdapter(EnvAdapter)` + `TravelTaskLoader(SplitDataLoader)` |
| `eval/optimizer/optimize.py` | driver CLI: cluster → target → trainer → proposed files + report |
| `eval/optimizer/skillopt_config.yaml` | trainer config: mixed gate, epochs, lr budget, model backends |
| `tests/test_skillopt_adapter.py` | adapter unit tests (rollout shaping, artifact materialization) with run_task stubbed |

### Modified files

| File | Change |
|------|--------|
| `agent/travel_agent.py` | call-time harness-config override: `load_harness_config` resolves explicit arg → `HARNESS_CONFIG_PATH` env var → default path (small refactor of Slice 2 code; behavior unchanged when env var unset) |
| `requirements.txt` / `pyproject.toml` | add `skillopt>=0.1.0` |

---

## The two targets, concretely

The trainer optimizes one text blob. What that blob *is* differs by target:

**Skill target** (`cluster.layer` startswith `skill:`)
- Artifact = the markdown body of `skills/<name>/SKILL.md` (frontmatter preserved separately, reattached on output — reuse `eval/skill_loader.py`).
- Rollout: write candidate body to a temp skill dir (`<out_dir>/candidate_skill/SKILL.md` with original frontmatter), call `run_task(task, skill_path=temp_dir, condition="with_skill")` per task.

**Harness target** (`cluster.layer` startswith `harness:`)
- Artifact = the **value of one optimizable key** from `agent/harness_config.yaml` (e.g. the `base_system_prompt` string), selected from `cluster.target_artifact` (format `agent/harness_config.yaml::<key>`). Editing one key keeps edits bounded and the diff reviewable. For `tool_descriptions`/`node_prompts` (dict keys), the artifact is the YAML-serialized sub-dict.
- Rollout: load the real `harness_config.yaml`, substitute the candidate value, write the full config to `<out_dir>/candidate_harness_config.yaml`, set `HARNESS_CONFIG_PATH` to it, then run the tasks **in the condition that exposed the failure: `with_skill`, with the cluster's skill injected** (the 002/006 failures only manifest with the skill present). Unset the env var afterward (try/finally).

`optimizable` keys in the YAML are the whitelist; the driver refuses a target key not listed there.

## Adapter details

**`TravelTaskLoader(SplitDataLoader)`** — `load_raw_items()` returns one item per task dir for the cluster's domain: `{"id": task_dir.name, "question": instruction.md text, "task_type": domain, "task_path": str(task_dir)}`. `split_mode="ratio"`, ratio `"5:3:2"` (train/val/test), fixed seed from config → deterministic, persisted by the trainer's own state handling.

**`TravelEnvAdapter(EnvAdapter)`** — constructed with a `TargetSpec` (kind, key, skill_path, domain, tasks_dir, base harness config path). 
- `rollout(env, skill_content, out_dir)`: materialize the artifact per target kind (above), run `run_task` per item in the batch, return `[{"id", "hard": int(passed_verifier), "soft": float(score), "fail_reason": judge_reasoning, "task_type": domain}]`. Mock MCP must be up (same precondition as ab_compare; driver checks and fails fast with a clear message).
- `reflect(results, skill_content, out_dir)`: follow the built-in adapter pattern (officeqa/alfworld in the wheel are the reference implementations) — delegate to skillopt's reflection machinery (`skillopt.gradient.reflect`) so patches arrive in its native `RawPatch` format. The reflect prompt receives our failure context: task instruction, tools called vs expected, `fail_reason`.
- `get_task_types()`: `[domain]`. `requires_ray()`: False.

## Config (`eval/optimizer/skillopt_config.yaml`)

```yaml
model:
  backend: openai_chat          # optimizer-side LLM stages
  optimizer: gpt-4o             # stronger model proposes edits
train:
  num_epochs: 5
  learning_rate_budget: 3       # max accepted edits per epoch
evaluation:
  gate_metric: mixed            # NEVER hard at ≤10-task scale
  gate_mixed_weight: 0.5
```
(Exact key names to be finalized against `skillopt.config.flatten_config`'s `_FLATTEN_MAP` during implementation — the implementer must read that mapping, not guess.)

The eval-side model stays whatever `run_task` uses (gpt-4o-mini) — the trainer's "target model" setting is unused because our adapter owns rollout entirely.

## Driver (`eval/optimizer/optimize.py`)

```
python -m eval.optimizer.optimize --classification failure_classification.json [--cluster N] [--dry-run]
```
- Reads clusters; `--cluster` selects one, default = all qualifying (n_failures ≥ 1 for harness, ≥ 2 for skill — single-task skill clusters are too thin to optimize).
- Per cluster: resolve TargetSpec → preflight (mock MCP reachable, target key in `optimizable`, OPENAI_API_KEY set) → run trainer → emit proposed file + `optimization_report.json`.
- `--dry-run`: print resolved targets + splits + estimated rollout call count, run nothing.
- Report includes: baseline selection score, best selection score, held-out **test** score (the honest number), accepted/rejected edit counts, cost estimate (rollout calls × per-call cost from `eval/cost.py`).
- Exit honestly: if no candidate beats baseline on the test split, say so and write no proposed file.

## Cost/runtime envelope

One harness run, ancillery (10 tasks, 5/3/2): baseline + per-epoch candidate evals ≈ 100–250 `run_task` calls of gpt-4o-mini (~$0.05–0.15) plus optimizer-model calls (gpt-4o, ~10–30 calls). Minutes, not hours, with the mock MCP local. The driver prints the estimate before starting (and `--dry-run` shows it without spending).

## Safety rails (PRD §5.8.7, restated as requirements)

1. Output only `*_proposed.*` under `eval/optimizer_output/` — never writes to `agent/harness_config.yaml`, never to `skills/`, never commits.
2. Harness targets restricted to the `optimizable` whitelist in the YAML.
3. The held-out test split is evaluated exactly once, after training — selection-split scores are never reported as the headline number.
4. `HARNESS_CONFIG_PATH` is set per-rollout and always restored (try/finally) — a crashed run must not leave the agent pointed at a candidate config.

## Out of scope (Slice 3)

- Archive + Thompson-sampling bandit over strategies (Slice 4)
- Auto-PR opening (Slice 3b, after proposals prove trustworthy; `propose_skill.open_skill_pr` already exists for it)
- LLM fallback in the failure classifier
- Multi-cluster parallel optimization

## Risks

| Risk | Mitigation |
|------|-----------|
| skillopt 0.1.0 trainer has benchmark-shaped assumptions we'll fight | Reference implementations (officeqa, alfworld adapters) ship in the wheel; implementer follows them. If a contract proves unworkable mid-implementation, STOP and surface it — fallback posture is gate+types-only with our own loop (pre-approved alternative). |
| Trainer's internal LLM stages mis-configured → silent garbage edits | `--dry-run` first; report logs every accepted/rejected edit with diffs; test split is the arbiter. |
| 5/3/2 of 10 tasks = selection on 3 tasks → noisy gate | That is exactly why gate_metric=mixed; also report per-task selection scores so reviewers see the variance. |
| Optimizer "fixes" the harness in a way that breaks other domains | Proposed-only + human review; reviewer should run `ab_compare` on a second skill before merging a harness PR (noted in the report's review checklist). |
