# fare-rules — skill text update

**Target layer:** Skill (`travel-agent-skills/skills/fare-rules/SKILL.md`)
**Status:** Fix implemented and on PR (`fix/fare-rules-regressions`), awaiting merge
**Severity:** High — one failure mode executed a cancellation the user never asked for

## Evidence

CI gate runs on PR #1 (50 tasks × 5 trials, twice) showed three consistent
−1.00 regressions, all reproduced locally:

| Task | With-skill behavior | Why |
|---|---|---|
| fare-rules-121 | No tool call — asks clarifying question | Step 1 demanded confirming PNR/fare class even when the flight code was already given |
| fare-rules-129 | `get_itinerary` then stalls | Same confirm-first detour |
| fare-rules-143 | **Calls `cancel_booking`** on "what are the penalties if I cancel?" | Skill never stated it is information-only |

## Recommendation (implemented in the PR)

1. A flight code / booking reference already in the message is sufficient — never re-confirm it.
2. Retrieve rules in the same turn with the identifier provided; no lookup detours.
3. New edge case: the skill is informational — present fees via `get_fare_rules`;
   never call `cancel_booking`/`modify_booking` from a rules question.

## Verification

Local with-skill: 121/129/143 all score 1.0 with a single clean `get_fare_rules`
call; spot-checked passing tasks unaffected. Final verdict comes from the PR's
own CI gate run.
