# Detection suite — build report_judge eval infrastructure

**Target layer:** Eval platform (new verifier + new task domain), NOT the skills
**Status:** Designed, not built
**Severity:** Medium — 9 of 17 registered skills currently have zero eval coverage

## Why the existing verifiers can't grade these skills

The 9 sub-skills under `skills/disruption-skill/` are report-only by policy:
they detect, score severity, and emit PA-approval payloads — calling any action
tool is forbidden. `tool_call_check` would always score them 0; they are
allowlisted in `tests/test_skill_task_coverage.py` (REPORT_ONLY_SKILLS).

## Design

New verifier `report_judge`, three layers (cheapest first):

1. **Structural** — report parses and contains every field of the sub-skill's
   `references/schema.md`.
2. **Policy gate** — zero action tools called; any `cancel_booking` /
   `modify_booking` / `create_booking` call = instant 0.
3. **Judged correctness** — existing hardened LLM judge scores severity and
   cascade analysis against the task's known facts.

New taskgen domain `disruption_detection`, seeded from each sub-skill's schema
examples. Calibration bar changes: a no-skill agent will rarely produce a
schema-conformant report, so the bar becomes "baseline attempts a coherent
report", not pass/fail mix.

## Done when

Each detection sub-skill has ≥10 promoted tasks, its REPORT_ONLY_SKILLS entry
is removed, and the coverage test passes without the allowlist.
