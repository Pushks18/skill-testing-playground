# Phase 8 Orchestrator — Verdict: SHELVED

**Date:** 2026-06-08
**Decision:** Do not adopt orchestrated mode. `agent_mode="mono"` stays the default.
**Status:** Experiment complete. Code retained but dormant (opt-in only).

---

## The question

Phase 8 built an embedding router that picks one per-domain specialist agent
(scoped tools + always-injected skill) instead of running one general agent with
all skills/tools ("mono"). Does routing to focused specialists beat the generalist?

## The answer: no

Full bank comparison (141 tasks, 9 domains, 3 trials, best-of-N). Weighted delta
is orchestrated minus mono — negative means orchestrated is worse.

| Router policy | Overall weighted Δ | Domains worse | Better | Same | Misroutes |
|---|---|---|---|---|---|
| safe-fallback (`orchestrator_full_safe_fallback.json`) | **−0.0955** | 8 | 0 | 1 | 76 |
| capability-safe (`orchestrator_full_capability_safe.json`) | **−0.0607** | 6 | 2 | 1 | 62 |

Capability-safe was the better of the two and still loses across the board.
Worst domains: disruption (−0.19), booking_flow (−0.10), ancillery (−0.09).
Only fare_rules (+0.02) and itinerary_build (+0.06) edged positive.

## Why it loses

1. **Routing is lossy at this scale.** 62–76 misroutes out of 141 tasks. The
   embedding router + LLM tie-break is wrong often enough that the focus benefit
   never pays for itself.
2. **Tool scoping is where the damage is fatal.** The earlier iterations found
   that fatal misroutes (a required tool sitting outside the wrong specialist's
   subset) come from tool scoping, not routing per se. Keeping the top-1 skill
   with the full toolset (capability-safe) cut fatal misroutes from 10→1 but
   still couldn't beat mono — the generalist already has every tool and every
   skill description available, so it has strictly more to work with.
3. **No headroom to win.** Mono already scores high on most domains (fare_rules
   1.0, hotel 0.97, ancillery 0.93+). There is little a specialist can add and a
   lot a misroute can subtract.

## What we keep

- The router, specialists, and `orchestrator_compare` harness stay in the tree —
  they are useful for future experiments and the router accuracy report is a free
  diagnostic.
- `agent_mode="mono"` remains the default in `run_task`. Orchestrated mode is
  reachable via `agent_mode="orchestrated"` for anyone who wants to re-test (e.g.
  if the bank grows much larger, or skills become more numerous/specialized,
  routing economics could change).

## If revisited

Re-run `eval/orchestrator_compare.py` after a substantial bank/skill expansion.
The decision to adopt should require a **positive** overall weighted delta, not
just fewer fatal misroutes.
