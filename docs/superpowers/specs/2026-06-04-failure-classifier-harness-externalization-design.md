# Failure-Layer Classifier + Harness Externalization — Design

**Date:** 2026-06-04
**Status:** Approved for implementation
**Scope:** Slices 1+2 of PRD §5.8 (Optimization Architecture). Slice 3 (SkillOpt two-target optimizer) and Slice 4 (archive + bandit) are separate, later plans.
**Repo:** `skill-testing-playground`

---

## Motivation

An ancillery-skill eval run produced a BLOCK verdict (weighted delta −0.258, 30% regression rate). Three tasks regressed to delta −1.0:

| Task | no_skill | with_skill | Root cause |
|------|----------|------------|------------|
| ancillery-002 | `add_ancillary` ✓ | **no tools called** | agent responded verbally, never acted |
| ancillery-003 | `add_ancillary` ✓ | `get_itinerary` → `get_fare_rules` → stopped | over-verification loop, never reached `add_ancillary` |
| ancillery-006 | `add_ancillary` ✓ | **no tools called** | verbal-only |

These are **harness failures, not skill-content failures**. The skill injection caused the agent's reasoning layer to stop calling tools. Editing `SKILL.md` text in an optimization loop can never fix a no-tool-call failure — the lever is in the agent harness (base prompt, tool descriptions, node prompts).

Today the GRPO optimizer only proposes edits to `SKILL.md`. It would misattribute all three failures to the skill and churn skill text uselessly. The fix is a **failure-layer classifier** that routes each failure to the correct artifact, plus **externalizing the harness into config** so it becomes an editable optimization target.

This design builds the diagnostic + foundation. It does not build the optimizer itself.

---

## Slice 1: Failure-Layer Classifier

### Purpose

Read eval results, label each failed task by the layer that caused the failure, and cluster failures by `(layer, domain)` so a later optimizer can route each cluster to exactly one artifact.

### New file: `eval/classify_failures.py`

### Data flow

```
ab_results.json ──┐
                  ├──> extract_features(ABResult) ──> TrajectoryFeatures
trajectory.db  ───┘  (optional enrichment)                  │
                                                            ▼
                                              classify_layer(features) ──> FailureClassification
                                                            │
                                              cluster by (layer, domain) ──> FailureCluster[]
```

`ab_results.json` is the primary source — each `ABResult` already carries both `no_skill` and `with_skill` `EvalResult`s with `tools_called`, `tool_params`, `steps`, and `score`. `trajectory.db` is optional enrichment (step-level timings); the classifier must work from `ab_results.json` alone.

### New dataclasses (in `eval/schemas.py`)

```python
@dataclass
class TrajectoryFeatures:
    task_id: str
    domain: str
    task_weight: float
    skill_injected: bool
    # Tool behavior
    n_tools_called: int
    called_any_tool: bool
    first_tool_name: Optional[str]
    expected_first_tool: Optional[str]
    first_tool_correct: bool
    n_wrong_tool_calls: int
    n_repeated_tool_calls: int
    # Param quality
    n_calls_missing_required_params: int
    param_match_rate: float
    # Control flow
    n_steps: int
    step_delta_vs_no_skill: int
    ended_without_tool_on_tool_task: bool
    looped_without_completion: bool
    # Output / outcome
    output_is_verbal_only: bool
    verifier_score: float
    delta_vs_no_skill: float

@dataclass
class FailureClassification:
    task_id: str
    layer: Literal[
        "harness:base_prompt", "harness:tool_description",
        "harness:node_prompt", "skill:content",
        "skill:over_prescription", "skill:trigger",
    ]
    confidence: float
    target_artifact: str   # "agent/harness_config.yaml::base_system_prompt" or "skills/<name>/SKILL.md"
    evidence: dict         # the feature values that drove the decision

@dataclass
class FailureCluster:
    layer: str
    domain: str
    task_ids: list[str]
    dominant_failure_mode: str
    target_artifact: str
    n_failures: int
```

(Note: a separate `FailureCluster` already exists in `eval/optimizer/propose_skill.py` for the *new-skill* proposal path. That one clusters by domain for missing skills; this one clusters by `(layer, domain)` for existing-artifact routing. Keep them distinct — do not merge. The classifier's cluster lives in `schemas.py`; the propose_skill one stays where it is.)

### Classification logic — rules-first

`classify_layer` reuses the existing `classify_failure(tools_called, required_tools, required_params)` from `trajectory.py` to get the failure *mode*, then maps mode + features to a *layer*:

| Failure mode (existing) | + feature condition | → Layer | Confidence |
|-------------------------|---------------------|---------|------------|
| `NO_TOOL_CALL` | task requires a tool | `harness:base_prompt` | 0.9+ |
| `WRONG_TOOL` | tools were called, first wrong | `harness:tool_description` | 0.85 |
| any | `looped_without_completion` or high `step_delta_vs_no_skill` | `harness:node_prompt` | 0.8 |
| `MISSING_PARAM` / `MULTI_STEP_DROPOUT` | tool called, params bad | `skill:content` | 0.8 |
| any | fails only `with_skill` AND `delta_vs_no_skill <= -0.5` | `skill:over_prescription` | 0.85 |

Precedence: `skill:over_prescription` is checked first when the failure appears only in the `with_skill` condition and the delta is severe (this is the 002/006 signature: no_skill passed, with_skill scored 0). When both the over-prescription condition and a harness mode apply, prefer the harness label if `called_any_tool == False` (the actionable lever is the harness), and record the competing signal in `evidence`.

No LLM call in Slice 1. Every ancillery failure in the observed data is deterministically separable. An LLM fallback for low-confidence traces is a documented Slice-3 hook, not built here.

### Target-artifact resolution

- `harness:*` layers → `agent/harness_config.yaml::<key>` (base_system_prompt, tool_descriptions, node_prompts)
- `skill:*` layers → `skills/<skill_name>/SKILL.md` in `travel-agent-skills`

### CLI

```
python -m eval.classify_failures --results ab_results.json [--db trajectory.db]
```

Prints the per-task layer table and the clustered routing decision:

```
Failure classification (ab_results.json):
  ancillery-002  harness:base_prompt   (no tools called on tool task)   conf 0.94
  ancillery-003  harness:node_prompt   (verification loop, +1 step, no completion)  conf 0.82
  ancillery-006  harness:base_prompt   (verbal-only)                    conf 0.91
  → cluster: (harness:base_prompt, ancillery) 2 tasks → agent/harness_config.yaml::base_system_prompt
  → cluster: (harness:node_prompt, ancillery) 1 task  → agent/harness_config.yaml::node_prompts
  → NO skill PR proposed
```

Also writes `failure_classification.json` for downstream (Slice 3) consumption.

### Validation

Run against the real `ab_results.json` from the ancillery run. Acceptance: 002 and 006 classify as `harness:base_prompt`, 003 as `harness:node_prompt` (or `skill:over_prescription` with harness recorded as competing signal). None of the three classify as plain `skill:content`. This is the thesis check.

---

## Slice 2: Harness Externalization

### Purpose

Move the harness's editable surface (base prompt, tool descriptions, node prompts) out of Python and into `agent/harness_config.yaml`, so a harness edit is a clean config diff identical in shape to a `SKILL.md` edit. This is the "Option C: externalize first, then optimize" decision. Optimization itself is Slice 3 — this slice only externalizes, in a strictly behavior-preserving way.

### New file: `agent/harness_config.yaml`

```yaml
version: "1.0"

base_system_prompt: |
  You are a helpful travel assistant. Use the available tools to help
  users with flight searches, hotel bookings, and travel planning.

tool_descriptions:
  search_flights: "Search for available flights between two cities."
  search_hotels: "Search for available hotels at a location."
  check_availability: "Check if a flight or hotel resource is available on a date."
  get_fare_rules: "Get cancellation, change, and baggage rules for a flight."
  validate_passenger: "Validate passenger information before booking."
  create_booking: "Create a flight or hotel booking for a passenger."
  modify_booking: "Modify an existing booking (date change, upgrade, etc)."
  cancel_booking: "Cancel a booking and get refund information."
  get_itinerary: "Retrieve the full itinerary for a booking."
  add_ancillary: "Add an ancillary service to a booking. service_type: seat_selection, extra_baggage, travel_insurance, lounge_access, priority_boarding, car_rental, airport_transfer."

node_prompts: {}   # optional overrides; empty = current behavior

optimizable:
  - base_system_prompt
  - tool_descriptions.*
  - node_prompts.*
```

The initial values are **verbatim copies** of today's hardcoded strings. `node_prompts` starts empty — current code has no separate node prompts, so empty preserves behavior.

### Loading mechanism

```
build_travel_agent(skill_content, ...)
  └─> load_harness_config()            # new helper, module-level cached
        ├─> base_system_prompt         # replaces hardcoded string (line 112-115)
        ├─> tool_descriptions[name]    # assigned onto each tool post-construction
        └─> node_prompts (optional)    # appended to agent_node system msg only if present
```

### Tool-description injection

LangChain `@tool` reads its description from the docstring at decoration time. To make descriptions config-driven without rewriting the tool bodies, `make_mcp_tools` assigns `tool.description = config["tool_descriptions"][tool.name]` after the tools are constructed (post-construction assignment). Function bodies stay untouched.

### Backward-compatible fallback

If `agent/harness_config.yaml` is missing or a key is absent, `build_travel_agent` falls back to the current hardcoded values. Nothing breaks if the file isn't present (e.g. a CI checkout before the file is committed). The fallback strings live in the Python as the source-of-truth default; the YAML overrides them when present.

### Behavior-preservation — the critical constraint

This is a refactor, not a behavior change. If externalization shifts eval scores, the Slice-3 baseline is corrupted and its deltas become untrustworthy.

**Verification gate (must pass before Slice 2 is considered done):**
1. Capture the current ancillery `ab_results.json` (weighted delta, per-task scores) as the pre-refactor baseline.
2. Externalize.
3. Re-run the same ancillery eval.
4. Per-task scores and weighted delta must match the pre-refactor baseline within trial-to-trial noise. A structural mismatch (e.g. a tool description silently changed, or the base prompt altered) means the refactor is wrong and must be corrected before proceeding.

Because LLM eval has run-to-run variance, "match" means: same set of passing/failing tasks and weighted delta within the noise band already seen across trials — not bit-identical scores.

---

## What this design explicitly does NOT include

- The SkillOpt optimizer, mixed gate, held-out split, `*_proposed` file generation (Slice 3)
- Archive + Thompson-sampling bandit (Slice 4)
- LLM-as-classifier fallback (Slice 3 hook)
- Any auto-PR or auto-commit behavior
- Changes to `travel-agent-skills` (this is all `skill-testing-playground`)

---

## File-change summary

| File | Change |
|------|--------|
| `eval/schemas.py` | add `TrajectoryFeatures`, `FailureClassification`, `FailureCluster` |
| `eval/classify_failures.py` | new — feature extraction, layer classification, clustering, CLI |
| `agent/harness_config.yaml` | new — externalized base prompt, tool descriptions, node prompts |
| `agent/travel_agent.py` | load config; post-construction tool-description assignment; fallback defaults |
| `tests/` | classifier unit tests (incl. the 002/003/006 cases); harness config load + fallback tests |

---

## Commit policy

Per project convention: imperative style (`feat:`, `fix:`, `docs:`, `chore:`), no co-author attribution, each slice gets its own commit (or small commit series). Slice 1 and Slice 2 are independent commits.
