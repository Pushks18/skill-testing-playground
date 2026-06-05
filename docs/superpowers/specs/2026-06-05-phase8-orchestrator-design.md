# Phase 8: Multi-Agent Orchestrator — Design

**Date:** 2026-06-05
**Status:** Draft for review
**Scope:** PRD Phase 8 — replace the monolithic single agent with an embedding router + per-domain specialist agents. The LAST unbuilt item of the platform spec.
**Repo:** `skill-testing-playground`

---

## Motivation (now evidence-backed, not just roadmap)

The monolith carries one base prompt + all 10 tools + whatever skill is injected. Today's evidence says that hurts:
- **Context interference:** the base prompt has accumulated three ancillary-specific sentences (optimizer iterations 1–3); disruption tasks degraded when ANY skill was injected on top of it. Every domain pays attention-tax for every other domain's instructions.
- **Wrong-tool failures:** the classifier's `harness:tool_description` layer exists because 10 tools compete for selection. A specialist with 4 relevant tools cannot call the other 6.
- **Optimizer blast-radius:** tuning the shared base prompt for one domain risks all others (why we verify flight-search after every ancillery change). Per-agent prompts make harness optimization local.

## Architecture

```
user message ──► AgentRouter.route(text)            (embeddings, <1ms, no LLM)
                    │  SkillRouter (all-MiniLM-L6-v2, exists since Phase 2)
                    │  score < 0.35 → fallback: planning-skill agent
                    ▼
            SpecialistAgent for the matched skill
              = build_travel_agent(
                  skill_content = that skill's body (ALWAYS injected),
                  tools         = SKILL_TOOLS[skill]   ← scoped subset
                )
                    ▼
            normal LangGraph think→act loop, multi-turn affinity
            (conversation stays with the routed agent; no mid-conversation re-route)
```

### New files

| File | Responsibility |
|---|---|
| `agent/router.py` | `AgentRouter`: wraps `eval.skill_router.SkillRouter`, lazy-builds + caches one specialist per skill, `route(text) -> (skill_name, agent)`, fallback to planning-skill below threshold 0.35 |
| `agent/specialists.py` | `SKILL_TOOLS` map + `build_specialist_agent(skill_name, skills_root, mock_mcp_url)` |
| `eval/orchestrator_compare.py` | bank-wide mono-vs-orchestrated comparison + router accuracy report |
| tests for each | |

### Modified files

| File | Change |
|---|---|
| `agent/travel_agent.py` | `build_travel_agent(...)` gains optional `tools_subset: list[str] | None = None` — filters `make_mcp_tools` output by name; None = all 10 (existing behavior unchanged) |
| `eval/run_task.py` | optional `agent_mode: "mono" | "orchestrated" = "mono"` param: orchestrated mode ignores `skill_path`/`condition` injection and routes via AgentRouter (the router decides the skill) |

## Tool scoping — `SKILL_TOOLS`

Conservative: scope only the well-understood domains; anything unlisted gets all 10 tools (planning especially — it composes).

```python
SKILL_TOOLS = {
    "flight-search":      ["search_flights", "check_availability", "get_fare_rules"],
    "hotel-search":       ["search_hotels", "check_availability"],
    "booking-skill":      ["validate_passenger", "create_booking", "get_itinerary",
                            "check_availability", "search_flights", "search_hotels"],
    "fare-rules":         ["get_fare_rules", "get_itinerary"],
    "ancillery-skill":    ["add_ancillary", "get_itinerary", "get_fare_rules"],
    "modify-booking":     ["modify_booking", "get_itinerary", "check_availability",
                            "cancel_booking", "get_fare_rules"],
    "disruption-handling":["get_itinerary", "search_flights", "modify_booking",
                            "cancel_booking", "get_fare_rules", "validate_passenger"],
    # planning-skill: unlisted → all tools (it composes across domains)
}
```

The map is data, not architecture — it can move into each skill's frontmatter (`metadata.tools`) later; not in this phase (YAGNI until the skills repo wants it).

## Specialist prompt

Each specialist gets the SHARED `harness_config.yaml` base prompt + its skill body, exactly as `with_skill` runs do today — Phase 8 changes *which* skill+tools are present, not the prompt mechanics. Per-agent base-prompt overrides (e.g. stripping ancillary sentences from the flight agent) are a natural follow-up via `harness_config` per-skill keys — explicitly OUT of this phase to keep the comparison clean: the mono-vs-orchestrated eval must attribute deltas to routing+scoping alone.

## Multi-turn affinity

Route ONCE on the first user message; the conversation (multi-turn simulator rounds included) stays with that specialist. Re-routing mid-conversation on clarifying answers ("It's BK7Q2R8T") would misroute — refs score near zero against every skill description.

## Evaluation — `eval/orchestrator_compare.py`

Two questions, two measurements:

1. **Router accuracy (free, no agent calls):** route all 60 `trigger/labeled_requests.json` messages + all 141 task instructions; report precision/recall per skill vs labels (requests) and vs task.toml `skill` field (tasks). Target per PRD: P ≥ 0.85, R ≥ 0.80.
2. **End-to-end quality (paid):** run tasks in both modes — `mono` = today's `with_skill` behavior (the task's designated skill injected) vs `orchestrated` = router decides. Per-domain weighted deltas + a gate-style verdict. Supports `--domains` subset and `--trials N` for cost control. Misroutes are reported per task (routed skill ≠ designated skill) so quality deltas can be attributed to routing vs scoping.

Cost envelope: full bank × 2 modes × 3 trials ≈ 850 agent runs ≈ $0.25–0.50, ~20–30 min with the parallel harness. A `--domains ancillery,disruption --trials 3` pilot ≈ $0.05 first.

## Safety / rollback

- The orchestrator is OPT-IN (`agent_mode="orchestrated"`); nothing changes for existing evals, the optimizer, or CI until the comparison wins.
- No production wiring in this phase — eval-side only.
- If orchestrated loses, the artifact is still valuable: per-domain deltas tell us WHERE routing/scoping helps vs hurts.

## Out of scope

- Per-agent base-prompt overrides (follow-up; pairs with the optimizer's harness targets)
- LLM-based routing fallback for low-confidence matches (embedding-only per PRD cost table)
- Production/API server wiring of the orchestrator (`skill_server` detect endpoint already exposes routing separately)
- Moving SKILL_TOOLS into skill frontmatter

## Risks

| Risk | Mitigation |
|---|---|
| Router misroutes near-miss phrasings (delayed-flight baggage ask → disruption agent) | the 60-request dataset now contains exactly these traps; accuracy report surfaces them before any paid run |
| Scoped tools break a task needing an unlisted tool | conservative subsets err broad; misroute report + per-task tool data in results expose it |
| planning fallback becomes a dumping ground | report counts fallback routes explicitly |
| Specialist cache cold-start (9 agents × skill load) | lazy build + cache per process; skills are small files |
