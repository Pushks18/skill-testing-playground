# Stale A/B measurements — re-run four skills on the expanded banks

**Target layer:** Measurement (no artifact change)
**Status:** Queued — one command per skill
**Severity:** Medium — current scoreboard rows for these skills are not trustworthy

## Evidence

The task bank tripled (167 → 466) on Jun 10, but four skills were last measured
before the expansion:

| Skill | Last measured | Bank then | Bank now |
|---|---|---|---|
| ancillery-skill | Jun 6 | 20 | 50 |
| disruption-handling | Jun 6 | 12 | 50 |
| hotel-search | Jun 6 | 15 | 50 |
| flight-search | Jun 6 | 14 | 54 |

fare-rules demonstrated how much this matters: +0.167 on the old 16-task bank
became −0.023 on the 50-task bank — the new tasks found real failure modes.

## Command

```
LANGCHAIN_TRACING_V2=false .venv/bin/python eval/ab_compare.py \
  --skill-path ../travel-agent-skills/skills/<skill> --trials 3 \
  --output results/<skill>_ab_results.json
```

Expect new regressions to surface; route them through the standard
diagnose → fix → re-gate loop.
