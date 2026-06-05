# Archive + Bandit Layer (Slice 4) — Design

**Date:** 2026-06-05
**Status:** Draft for review
**Scope:** Slice 4 of PRD §5.8 (§5.8.5): the archive (population-based search memory) and the Thompson-sampling bandit over edit strategies. Builds directly on the working Slice 3 optimizer.
**Repo:** `skill-testing-playground`

---

## Motivation

The Slice 3 optimizer is stateless across runs: every run starts from the current artifact, steers the analyst with one fixed prompt, and forgets every candidate it generated. Two costs:

1. **No stepping stones.** Iteration 2's winning prompt was reachable only because iteration 1's output had been *manually applied* first. Variants that scored well but weren't promoted are lost entirely — including the rejected epoch-3 candidate whose diff might inform a later run.
2. **No strategy learning.** The analyst prompt steers the same way for a `NO_TOOL_CALL` base-prompt failure as for a `MISSING_PARAM` skill failure. Over runs, we accumulate evidence about *which kind of edit fixes which kind of failure* — and currently throw it away.

The archive fixes (1); the bandit fixes (2). Both are PRD §5.8.5, adapted to the SkillOpt-trainer loop that now exists (the PRD predates Slice 3's implementation details).

## What "strategy" means now (adaptation from the PRD)

The old `variant_strategies.py` strategies were full-rewrite prompts for the retired pseudo-GRPO loop. In the SkillOpt loop, the analyst is steered by our authored `analyst_error` prompt (`eval/optimizer/skillopt_prompts.py`). A **strategy is now a steering directive appended to that analyst prompt for the whole run**:

| Strategy key | Directive essence | Expected sweet spot |
|---|---|---|
| `push-tool-action` | edits must push the agent to CALL tools rather than answer verbally | `harness:base_prompt` / NO_TOOL_CALL |
| `broaden-coverage` | generalize trigger phrasings/examples so more request variants match | trigger-misses like the lounge-access case |
| `tighten-specificity` | narrow over-broad instructions that cause wrong-tool or over-trigger | `harness:tool_description`, `skill:over_prescription` |
| `add-edge-case` | document the exact failing case with explicit handling steps | `skill:content` edge failures |
| `simplify` | remove/condense instructions that distract the agent | over-prescription, long artifacts |

One arm pull per optimizer run (not per epoch): attribution is clean — the run's reward is `report["improved"]` (proposal written = gate-accepted edits + test non-regression). Per-epoch pulls would give more signal but murky attribution through the merge/gate stages; revisit only if run volume grows.

**Bandit conditioning key:** the cluster's `layer` (e.g. `harness:base_prompt`) — our routing taxonomy, stabler than the legacy failure modes.

## Components

### 1. Archive — `eval/optimizer/archive.py`

Append-only JSONL at `eval/optimizer_output/archive.jsonl` (git-committable, human-greppable). One entry per *meaningful candidate*: the run's initial artifact, every accepted step candidate, and the final best — with scores from the trainer's own records (`history.json`, `skills/skill_v*.md` under each run's out_root).

```python
@dataclass
class ArchiveEntry:
    entry_id: str            # uuid
    run_tag: str
    target: str              # "harness:base_system_prompt" | "skill:<name>"
    layer: str               # cluster layer that motivated the run
    strategy: str            # bandit arm used for the run
    content_hash: str        # sha256 of artifact text (dedupe)
    artifact_text: str       # the candidate text itself (artifacts are small)
    parent_hash: str | None  # hash of the artifact this was derived from
    selection_score: float | None
    test_score: float | None # only for promoted/final candidates
    accepted: bool           # did the trainer's gate accept it
    embedding: list[float]   # all-MiniLM-L6-v2 (384-d), reuses eval/skill_router.py's model
    created_at: str
```

API: `Archive.add(entry)`, `Archive.entries(target=...)`, `Archive.pick_parent(target, current_text, epsilon=0.2, seed=...)`.

**Parent selection (population-based search, the HyperAgents borrow):** at run start the driver currently seeds `skill_init` from the live artifact. With the archive: ε-greedy — with prob 1−ε use the live artifact (default behavior, safety anchor); with prob ε pick the archive entry for this target maximizing `selection_score − λ·cosine_sim(embedding, current)` (good *and* different = stepping stone). Every pick is recorded in the run report (`seed_source`). Propose-only safety is unchanged — exploration only affects the *starting point* of a run, never what gets written where.

### 2. Bandit — `eval/optimizer/bandit.py`

PRD §5.8.5's `BanditState`, persisted as JSON at `eval/optimizer_output/bandit_state.json`:

```python
@dataclass
class BanditState:
    arms: dict[str, tuple[float, float]]   # "layer|strategy" -> (alpha, beta), Beta(1,1) prior

    def select_strategy(self, layer: str, strategies: list[str], seed=None) -> str   # Thompson sampling
    def update(self, layer: str, strategy: str, reward: bool) -> None
    # plus load/save helpers
```

Fully interpretable: `python -m eval.optimizer.bandit --show` prints arm posteriors as a table.

### 3. Wiring in `optimize.py` (the only behavioral change to the driver)

```
run_cluster:
  strategy = bandit.select_strategy(cluster.layer, STRATEGIES)      # or --strategy override
  seed_text, seed_source = archive.pick_parent(...) if --explore else (live artifact, "live")
  adapter = TravelEnvAdapter(..., strategy_directive=STRATEGY_DIRECTIVES[strategy])
  ... trainer runs as today ...
  archive.add(initial + accepted candidates + best, with scores from out_root records)
  bandit.update(cluster.layer, strategy, reward=report["improved"])
  report += {"strategy": ..., "seed_source": ..., "bandit_posterior_after": ...}
```

`TravelEnvAdapter` gains `strategy_directive: str = ""`; `reflect()` appends it to the resolved `error_system` prompt. Empty directive = today's behavior exactly.

### 4. Defaults and flags

- Exploration (`pick_parent`) is **opt-in** via `--explore` for now — at the current handful-of-entries scale the archive mostly records; exploitation of it becomes useful as entries accumulate.
- `--strategy <key>` manual override skips the bandit pull (still records the outcome to that arm).
- Everything degrades gracefully: missing archive/bandit files = empty archive, uniform priors.

## Honest expectations at current scale

With ~1 optimizer run per failure cluster per week, the bandit needs *months* to separate arms statistically. That is fine and is stated up front: Slice 4's immediate value is (a) the archive as a permanent, searchable record of every candidate and score (already useful for review and debugging), (b) strategy steering as a *capability* (manual `--strategy` is immediately useful), and (c) the learning loop being in place so the data accumulates from day one rather than being discarded. The bandit's posteriors are honest about their own uncertainty — that is the point of Thompson sampling.

## File map

| File | Change |
|---|---|
| `eval/optimizer/archive.py` | new — ArchiveEntry, JSONL store, pick_parent |
| `eval/optimizer/bandit.py` | new — BanditState, Thompson sampling, CLI --show |
| `eval/optimizer/skillopt_prompts.py` | add STRATEGY_DIRECTIVES dict (5 directives) |
| `eval/optimizer/skillopt_adapter.py` | `strategy_directive` param appended to error_system in reflect |
| `eval/optimizer/optimize.py` | bandit pull → directive; archive recording; bandit update; `--strategy`/`--explore` flags; report fields |
| `tests/test_archive.py`, `tests/test_bandit.py` | new |
| `tests/test_skillopt_adapter.py`, `tests/test_optimize_driver.py` | extended |

## Out of scope

- Per-epoch strategy switching (attribution murk; revisit with run volume)
- Cross-target transfer (bandit arms are per-layer, not shared)
- Auto-pruning/consolidation of the archive
- Any change to propose-only/human-review guarantees

## Risks

| Risk | Mitigation |
|---|---|
| sentence-transformers model load (~80MB) slows driver startup | lazy import; embed only on `add()`; `--no-embed` escape hatch storing `[]` |
| Bandit overfits to tiny reward counts | Beta(1,1) priors + Thompson sampling are exactly the right behavior under scarcity; `--show` exposes uncertainty |
| Archive JSONL grows with embeddings | ~8KB/entry; at our run volume, years before it matters |
| Strategy directive degrades the analyst prompt | empty-directive default = current behavior; directives are short appended steering lines, gate still arbitrates |
