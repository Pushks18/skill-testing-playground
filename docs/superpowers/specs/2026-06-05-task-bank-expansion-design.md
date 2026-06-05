# Task Bank Expansion (73 → ~141) — Design

**Date:** 2026-06-05
**Status:** Approved direction (focused doubling), spec for implementation
**Repo:** `skill-testing-playground`
**Priority context:** chosen over Slice 4 (archive + bandit) because every structural pain in Slices 1–3 — split starvation, single-failure duplication hacks, 3-task selection gates, flaky-task ambiguity — traces to N=10 per domain. Data first; learning systems after.

---

## Targets (focused doubling)

| Domain | Now | Target | New | Rationale |
|---|---|---|---|---|
| ancillery | 10 | 20 | +10 | optimizer home turf; unblocks 10/6/4 splits |
| booking_flow | 8 | 20 | +12 | weight-3.0 revenue-critical, currently among thinnest |
| fare_rules | 6 | 16 | +10 | too thin to split |
| itinerary_build | 6 | 16 | +10 | too thin to split |
| **disruption (NEW)** | 0 | 12 | +12 | empty domain; future Phase-6 auto-skill candidate |
| edge_cases | 10 | 16 | +6 | hard-case coverage |
| flight_search | 10 | 14 | +4 | modest top-up |
| trip_planning | 8 | 12 | +4 | modest top-up |
| hotel_search | 15 | 15 | 0 | already deep |
| **Total** | **73** | **~141** | **+68** | |

## Generation — `eval/taskgen.py` (new module)

Per-domain LLM batches (existing OpenRouter/OpenAI client pattern). Each generation call receives:
- the domain description + its skill mapping (task.toml `skill` field; disruption → `disruption-handling`, a skill that does not exist yet — that is fine and intentional)
- the 10 mock-MCP tool signatures (so `expected.tools` are real)
- 3 existing tasks of that domain as few-shot format examples
- ALL existing instructions of that domain as a don't-duplicate list
- diversity directives: **paraphrase families** (same intent, varied surface form — the lounge-access lesson), **missing-info cases** (agent should ask, not fabricate), **multi-step compositions** (booking_flow, disruption)

Drafts land in a staging dir `tasks_drafts/<domain>/<task-id>/` (task.toml + instruction.md), NEVER directly in `tasks/`.

Disruption tasks compose existing tools only: rebooking = `search_flights`+`modify_booking`; cancellation = `cancel_booking`+`get_fare_rules`; compensation advice = `llm_judge` verifier. No mock-server changes.

## QC pipeline — 4 gates, in order

1. **Structural** (`taskgen validate`): task.toml parses (incl. the inline-table quirk), required fields present, `verifier ∈ {tool_call_check, llm_judge}`, `expected.tools` ⊆ the 10 real tools, id matches dir name, instruction.md non-empty.
2. **Near-duplicate** (`taskgen dedupe`): MiniLM embeddings (model already in stack via skill_router); cosine > 0.90 against any existing or in-batch instruction → reject draft.
3. **Discriminative power** (`taskgen calibrate`): run each surviving draft ONCE `no_skill` against the mock MCP (~$0.0002/task). Classify: `baseline-pass` / `baseline-fail` / `broken` (errors, impossible verifier). Target mix per domain ≈ 60% baseline-pass / 40% baseline-fail; `broken` drafts are cut or fixed. The mix matters: all-passing tasks give zero optimization signal; all-failing suggests bad tasks rather than hard ones.
4. **Human review**: a per-domain review sheet (`tasks_drafts/<domain>/REVIEW.md`: one row per draft — id, instruction, expected tools, calibration result). The human edits/rejects, then `taskgen promote --domain <d>` moves approved drafts into `tasks/`. Nothing enters `tasks/` without this step.

## Code changes beyond taskgen

- `eval/gate_check.py`: add `"disruption": 2.0` to `TASK_WEIGHTS`.
- Nothing else — loaders discover tasks dynamically from `tasks/`.

## Verification after promotion

- Full structural sweep: every task in `tasks/` passes gate 1.
- `ab_compare --skill-path .../ancillery-skill` smoke on the expanded domain: confirms 20-task discovery and that splits in a future optimizer run will be 10/6/4.
- Counts match the target table.

## Out of scope now → recorded as future work

1. **Trigger-eval labeled-request expansion.** The 30-message labeled dataset (`eval/trigger/labeled_requests.json`) tests *routing* accuracy — "does the agent pick the right skill for a message" — not task execution. Should grow alongside the bank (target ~60: positives for the new disruption domain, near-misses between ancillery/disruption, more no-skill negatives). Small standalone job; do after this expansion so new-domain positives exist to label.
2. **New mock-MCP endpoints.** Deliberately avoided here: disruption tasks compose the existing 10 tools, which is cheaper AND tests realistic tool composition. Revisit only if a future domain genuinely cannot be expressed with the current tool set (candidate: a dedicated `rebook_flight` if disruption tasks show composition is unreliable in practice).
3. **Docker task sandboxing.** The borrowed BenchFlow format supports one-container-per-task isolation; we run directly against the local mock server (faster, simpler). Becomes important when tasks gain side effects or run untrusted code — neither is true today. Revisit at CI-scale or when staging-MCP (real API) tasks arrive.

Also out of scope:
- Authoring the `disruption-handling` skill (deliberately left for the Phase-6 auto-generation pipeline, per PRD open question #3)
- Slice 4 archive/bandit (deferred behind this expansion — data first)

## Risks

| Risk | Mitigation |
|---|---|
| LLM drafts reference data the mock can't serve | mock returns plausible fake data for arbitrary inputs; calibration (gate 3) catches genuinely broken interactions |
| Paraphrase families flagged as duplicates | 0.90 cosine threshold tuned to allow same-intent-different-surface; calibration report shows rejected pairs for human override |
| Review fatigue (68 drafts) | review sheets are skimmable tables; per-domain batches reviewable independently; gates 1–3 pre-filter so the human sees only viable drafts |
| Calibration single-trial noise | acceptable for a coarse pass/fail/broken triage; not used as a precision metric |
