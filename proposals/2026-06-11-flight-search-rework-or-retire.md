# flight-search — rework or retire the skill

**Target layer:** Skill (`travel-agent-skills/skills/flight-search/SKILL.md`)
**Status:** Decision needed
**Severity:** Low urgency, real cost

## Evidence

Weighted Δ is exactly **0.000 across four separate evals** (Jun 5–6, four
different configurations). The no-skill agent already handles flight-search
tasks perfectly — the bank's baseline-pass rate for this domain is the highest
of all domains — so the skill adds ~2× input tokens per call and changes no
outcomes.

## Options

1. **Retire**: remove from routing for simple searches; keep the harness-only
   path. Cheapest, immediate token savings.
2. **Rework upward**: re-aim the skill at the hard 20% (multi-city, flexible
   dates, no-availability fallbacks) where new 50-task-bank failures may exist —
   wait for the post-expansion re-run before deciding.

## Recommendation

Run the stale-bank re-measure first (see stale-reruns proposal). If Δ stays
≈ 0 on the 54-task bank, retire the skill from routing and keep the file as
documentation.
