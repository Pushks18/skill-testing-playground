# Improvement Proposals

One file per active proposal. Each names its **target layer** (skill text,
harness config, tasks, or eval infra), the **evidence** behind it, and a
**status**. The optimizer's raw machine proposals live in
`eval/optimizer_output/<run>/`; the files here are the curated, human-readable
queue. The Task Bank UI (Improvement Proposals tab) renders this folder.

## Current queue — which layer needs what

| Skill / area | Layer needing update | Evidence | Status |
|---|---|---|---|
| fare-rules | **Skill text** | 3 consistent −1.00 regressions in CI (121/129/143); skill executed `cancel_booking` on a rules question | Fix PR open on personal fork |
| flight-search | **Skill text (rework or retire)** | Weighted Δ exactly 0.000 across 4 evals — pays 2× tokens for nothing | Decision needed |
| disruption-handling | **Re-measure first** | +0.132 but 25% regressions, measured pre-proposals on the old 12-task bank | Re-run queued |
| hotel-search, ancillery-skill | **Re-measure only** | PASS but measured on pre-expansion banks | Re-run queued |
| planning-skill | **Monitor** | +0.044 PASS; residual itinerary regressions are judge-content deltas, not tool failures | Watch next runs |
| modify-booking | **Skill text (optional polish)** | Aggregate +0.010 PASS but edge-datechange trio still individually negative | Low priority |
| booking-skill | **None** | +0.001 PASS, 2% regressions, zero flagged criticals | Healthy |
| Harness `node_prompts` | **None — stop targeting** | Two optimizer runs produced no-ops; the key is empty and no failure evidence points at it | Closed |
| Detection suite (9 skills) | **Eval infra, not the skills** | Report-only skills have no verifier; need `report_judge` + a detection task domain | Designed, not built |
| Model weights | **New layer** | "Asks instead of acts" reflex recurs across 4 skills despite prompt fixes | Designed (fine-tuning Path A) |

## How a proposal becomes a change

1. Evidence accumulates (A/B regressions, optimizer report, CI gate failure).
2. A proposal file lands here naming layer + evidence + recommendation.
3. A human applies the curated edit (or rejects it) — never auto-applied.
4. The full A/B gate re-judges; the proposal file gets a resolution note.
