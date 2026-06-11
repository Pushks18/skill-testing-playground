# Weights layer — API fine-tuning as the third optimization target

**Target layer:** Model weights (new), alongside skill text and harness config
**Status:** Designed; ~1-day build
**Severity:** Strategic — addresses the one failure class prompt edits keep re-fighting

## Evidence

The same behavioral failure — *agent asks/explains instead of calling tools* —
has now required prompt surgery in four separate skills (planning, booking,
modify-booking, fare-rules). Instructions fight the model's trained caution on
every call; examples retrain the reflex once.

## Design (Path A — no GPU anywhere)

1. Harvest passing trajectories from trajectory.db — **train-split tasks only**,
   never the gate's test tasks.
2. Build SFT JSONL (system + user + correct assistant tool_calls).
3. `fine_tuning.jobs.create(model="gpt-4o-mini-...")` — ~$3–10/run, 20–60 min.
4. A/B the returned `ft:` model id against base with the existing gate:
   `EVAL_MODEL=ft:... eval/ab_compare.py` — full cross-skill regression check
   mandatory (a tuned act-reflex must not start modifying bookings on
   innocent questions).
5. New bandit arm `weights:sft` records win/loss like any strategy.

## Trade-offs accepted

Hours-long feedback loop vs minutes; 2× per-token inference price on tuned
models (possibly offset by shrinking skill prompts); opaque diffs — behavior
is the only review surface, so the gate is the only safety net.

## Deliverables

`eval/optimizer/finetune.py` (harvest → JSONL → train → poll → auto-A/B),
bandit arm, `EVAL_MODEL` plumbed through the CI eval workflow.
