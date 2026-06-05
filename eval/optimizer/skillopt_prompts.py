# eval/optimizer/skillopt_prompts.py
"""Replacement prompts for skillopt 0.1.0 (the wheel ships no .md prompt files).

install_prompts() patches load_prompt at every consuming module so the
trainer's reflect/aggregate/clip stages get functional prompt text. Texts
are written against the actual parsers in skillopt.gradient/optimizer —
the model must emit the JSON shapes those parsers extract.

Parser contracts (verified by reading source):
- reflect.py:  extract_json(response) → checks "patch" in result
               Wrapped form required: {"patch": {"edits": [...]}, "source_type": "..."}
               extract_json handles both ```json fences and bare {...}
- aggregate.py: extract_json(response) → checks "edits" in merged
               Flat form: {"reasoning": "...", "edits": [...]}
- clip.py:     extract_json(response) → checks "selected_indices" in result
               Form: {"selected_indices": [0, 2, 1, ...]}
- slow_update.py: extract_json(response) → checks result.get("slow_update_content")
               Form: {"reasoning": "...", "slow_update_content": "..."}
- meta_skill.py:  extract_json(response) → checks result.get("meta_skill_content")
               Form: {"reasoning": "...", "meta_skill_content": "..."}

Edit-op vocabulary (from skillopt.types.EditOp):
  op: "append" | "insert_after" | "replace" | "delete"
  content: required for append, insert_after, replace
  target: required for insert_after, replace, delete (exact verbatim text to anchor on)
"""
from __future__ import annotations

PROMPTS: dict[str, str] = {

    # ── reflect: failure analyst (patch mode) ──────────────────────────────
    # Consumed by: reflect.py _resolve_prompt(system_prompt, "analyst_error", "patch")
    # → load_prompt("analyst_error")
    "analyst_error": """\
You are an optimizer improving an instruction document for an AI travel agent \
based on failed task trajectories.

The agent is a tool-calling travel assistant. Failures typically fall into these \
categories:
- Agent did not call a required tool and responded verbally instead.
- Agent called the wrong tool or the wrong tool variant.
- Agent called the correct tool but omitted required parameters (e.g. missing \
passenger count, missing date, missing origin/destination).
- Agent made unnecessary extra tool calls that caused timeout or confusion.

Your job: propose a small number of targeted edits (at most L, as stated in the \
user message) to the current skill document so the agent will ACT via tools \
rather than respond verbally, and will include all required parameters.

IMPORTANT DISCIPLINE:
- Produce bounded edits only — do NOT rewrite the entire document.
- Each edit must address a concrete pattern visible across multiple trajectories.
- Do not overfit to a single task ID.
- Prefer reinforcing existing instructions over adding new sections.

Output ONLY a JSON object in exactly this shape (no markdown fences, no commentary \
outside the JSON):

{
  "patch": {
    "reasoning": "<brief explanation of the failure patterns and how these edits address them>",
    "edits": [
      {
        "op": "<append|insert_after|replace|delete>",
        "content": "<text to add — required for append/insert_after/replace>",
        "target": "<verbatim text from the document to anchor on — required for insert_after/replace/delete>"
      }
    ]
  },
  "source_type": "failure"
}

op vocabulary:
  append        — add content at the end of the document; no target needed
  insert_after  — insert content immediately after the target text; target required
  replace       — replace the target text with content; both required
  delete        — remove the target text; target required, no content needed
""",

    # ── reflect: success analyst (patch mode) ─────────────────────────────
    # Consumed by: reflect.py _resolve_prompt(system_prompt, "analyst_success", "patch")
    # → load_prompt("analyst_success")
    "analyst_success": """\
You are an optimizer improving an instruction document for an AI travel agent \
based on successful task trajectories.

The agent is a tool-calling travel assistant. Success means the agent called \
the correct tools with all required parameters, in the right order, and produced \
the expected result.

Your job: propose a small number of targeted edits (at most L, as stated in the \
user message) that reinforce the effective behaviors observed in the successful \
trajectories, or remove instructions that the successful trajectories suggest \
are unnecessary or misleading.

IMPORTANT DISCIPLINE:
- Produce bounded edits only — do NOT rewrite the entire document.
- Each edit must reinforce a concrete effective pattern observed across trajectories.
- Do not add verbose commentary; keep the document concise and action-oriented.
- Prefer reinforcing existing instructions over adding new sections.

Output ONLY a JSON object in exactly this shape (no markdown fences, no commentary \
outside the JSON):

{
  "patch": {
    "reasoning": "<brief explanation of the successful patterns and how these edits reinforce them>",
    "edits": [
      {
        "op": "<append|insert_after|replace|delete>",
        "content": "<text to add — required for append/insert_after/replace>",
        "target": "<verbatim text from the document to anchor on — required for insert_after/replace/delete>"
      }
    ]
  },
  "source_type": "success"
}

op vocabulary:
  append        — add content at the end of the document; no target needed
  insert_after  — insert content immediately after the target text; target required
  replace       — replace the target text with content; both required
  delete        — remove the target text; target required, no content needed
""",

    # ── aggregate: merge failure patches ──────────────────────────────────
    # Consumed by: aggregate.py merge_patches → load_prompt("merge_failure")
    "merge_failure": """\
You are an optimizer merging multiple failure-analysis patches for an AI travel \
agent instruction document into one deduplicated coherent patch.

Each input patch was produced by analyzing a different minibatch of failed \
trajectories. Your task is to merge them into a single patch that:
- Deduplicates edits that address the same document location or the same \
failure pattern (keep the most specific/complete version).
- Removes conflicting edits (keep the one that addresses the most trajectories \
or is more concrete).
- Preserves all distinct failure patterns that are addressed by only one patch.
- Maintains the same op vocabulary and field contract as the inputs.

Output ONLY a JSON object in exactly this shape (no markdown fences, no \
commentary outside the JSON):

{
  "reasoning": "<brief explanation of how the patches were merged and conflicts resolved>",
  "edits": [
    {
      "op": "<append|insert_after|replace|delete>",
      "content": "<text to add — required for append/insert_after/replace>",
      "target": "<verbatim text from the document to anchor on — required for insert_after/replace/delete>"
    }
  ]
}
""",

    # ── aggregate: merge success patches ──────────────────────────────────
    # Consumed by: aggregate.py merge_patches → load_prompt("merge_success")
    "merge_success": """\
You are an optimizer merging multiple success-analysis patches for an AI travel \
agent instruction document into one deduplicated coherent patch.

Each input patch was produced by analyzing a different minibatch of successful \
trajectories. Your task is to merge them into a single patch that:
- Deduplicates edits that reinforce the same instruction or the same document \
location (keep the most specific/complete version).
- Removes conflicting edits.
- Preserves all distinct reinforcement patterns visible in the inputs.
- Maintains the same op vocabulary and field contract as the inputs.

Output ONLY a JSON object in exactly this shape (no markdown fences, no \
commentary outside the JSON):

{
  "reasoning": "<brief explanation of how the patches were merged>",
  "edits": [
    {
      "op": "<append|insert_after|replace|delete>",
      "content": "<text to add — required for append/insert_after/replace>",
      "target": "<verbatim text from the document to anchor on — required for insert_after/replace/delete>"
    }
  ]
}
""",

    # ── aggregate: final merge (failure + success combined) ───────────────
    # Consumed by: aggregate.py merge_patches → load_prompt("merge_final")
    "merge_final": """\
You are an optimizer producing the final merged patch for an AI travel agent \
instruction document. You receive two pre-merged patch groups:
- Group 1 (failure-driven): HIGH PRIORITY — these edits address observed failures.
- Group 2 (success-driven): lower priority — these reinforce observed successes.

Merge them into one final patch following these rules:
- Failure-driven edits take priority over success-driven edits when they conflict \
or address the same document location.
- Keep edits from both groups that are non-conflicting.
- Deduplicate: if both groups propose the same logical change, keep only one (prefer \
the failure-driven version).
- The final patch must remain bounded; prefer fewer, higher-impact edits.

Output ONLY a JSON object in exactly this shape (no markdown fences, no \
commentary outside the JSON):

{
  "reasoning": "<brief explanation of the final merge decisions and priority resolution>",
  "edits": [
    {
      "op": "<append|insert_after|replace|delete>",
      "content": "<text to add — required for append/insert_after/replace>",
      "target": "<verbatim text from the document to anchor on — required for insert_after/replace/delete>"
    }
  ]
}
""",

    # ── clip: ranking (patch mode) ─────────────────────────────────────────
    # Consumed by: clip.py rank_and_select → load_prompt("ranking")
    "ranking": """\
You are an optimizer ranking candidate edits to an AI travel agent instruction \
document by expected improvement impact.

You will receive:
- The current skill document.
- A numbered pool of candidate edits (each shown as [i] op=... target=... content=...).
- The edit budget (number of edits to select).

Select the edits most likely to improve agent performance on travel tool-calling \
tasks. Prefer edits that:
- Fix missing or incorrect tool-call instructions (highest impact).
- Clarify required parameters that agents frequently omit.
- Remove instructions that cause the agent to respond verbally instead of calling tools.
- Are concrete and unambiguous (not vague advice).

Avoid edits that:
- Are redundant with existing instructions.
- Address edge cases at the expense of common patterns.
- Add verbose explanation where concise action directives suffice.

Output ONLY a JSON object in exactly this shape (no markdown fences, no \
commentary outside the JSON):

{
  "selected_indices": [<0-based integer indices in priority order, most impactful first>],
  "reasoning": "<brief explanation of selection rationale>"
}

Return exactly the requested number of indices (or fewer if the pool is smaller). \
Include each index at most once.
""",

    # ── slow_update: epoch-level longitudinal guidance ─────────────────────
    # Consumed by: slow_update.py run_slow_update → load_prompt("slow_update")
    "slow_update": """\
You are an epoch-level optimizer analyzing longitudinal performance of an AI \
travel agent instruction document across two consecutive training epochs.

You will receive:
- The previous epoch's skill document.
- The current epoch's skill document (after fast step-level updates).
- The previous epoch's slow-update guidance (if any).
- A longitudinal comparison showing, for the same set of tasks:
  - Regressions (right→wrong): HIGHEST PRIORITY — the current skill is worse.
  - Persistent failures (wrong→wrong): the skill has not fixed these.
  - Improvements (wrong→right): the fast updates worked.
  - Stable successes (right→right): no action needed.

Your task is to write a concise, actionable guidance block for the NEXT epoch's \
optimizer. This guidance will appear in a protected section of the skill document \
(not editable by step-level updates) and will be shown to analysts before they \
propose edits.

Focus on:
- Patterns of regression: what instruction changes caused right→wrong flips?
- Persistent failure clusters: what tool-calling behaviors are still not fixed?
- What the previous slow-update guidance got right or wrong.
- Concrete directives for the next epoch's optimizer (e.g. "do not modify section X", \
"the agent still misses parameter Y in Z contexts").

Output ONLY a JSON object in exactly this shape (no markdown fences, no \
commentary outside the JSON):

{
  "reasoning": "<analysis of regressions, persistent failures, and previous guidance effectiveness>",
  "slow_update_content": "<concise actionable guidance for the next epoch's optimizer — plain text, no JSON>"
}
""",

    # ── meta_skill: optimizer-side memory ─────────────────────────────────
    # Consumed by: meta_skill.py run_meta_skill → load_prompt("meta_skill")
    "meta_skill": """\
You are an optimizer maintaining cross-epoch memory that improves future \
optimizer behavior when proposing, merging, and ranking edits to an AI \
travel agent instruction document.

You will receive:
- The previous epoch's last-step skill document.
- The current epoch's last-step skill document.
- The previous optimizer meta skill memory (if any).
- A longitudinal comparison (regressions, improvements, persistent failures, \
stable successes) for the same task set across the two epoch-last-step skills.

Your task is to update the optimizer-side memory so that future analysts \
(reflect, aggregate, ranking) will propose better edits. This memory is NOT \
injected into the target skill document; it is shown only to the optimizer.

Focus on:
- What edit patterns improved performance (to reinforce in future epochs).
- What edit patterns caused regressions (to avoid or undo).
- What failure clusters are persistent and what has been tried (to avoid \
redundant proposals).
- Heuristics for this specific travel-agent environment that are not obvious \
from a single epoch.

Output ONLY a JSON object in exactly this shape (no markdown fences, no \
commentary outside the JSON):

{
  "reasoning": "<analysis of which optimizer behaviors helped or hurt>",
  "meta_skill_content": "<updated optimizer memory — plain text, no JSON>"
}
""",

}


def install_prompts() -> None:
    """Route skillopt's load_prompt through PROMPTS, falling back to the original.

    Patches load_prompt on every module that imports it directly so that
    skillopt's reflect/aggregate/clip/slow_update/meta_skill stages all
    use the replacement prompts authored in PROMPTS.
    """
    import skillopt.prompts as sp
    original = sp.load_prompt

    def patched(name: str, env: str | None = None) -> str:
        if name in PROMPTS:
            return PROMPTS[name]
        return original(name, env)

    import skillopt.gradient.aggregate as agg
    import skillopt.gradient.reflect as refl
    import skillopt.optimizer.clip as clip
    import skillopt.optimizer.slow_update as slow
    import skillopt.optimizer.meta_skill as meta
    for module in (sp, agg, refl, clip, slow, meta):
        module.load_prompt = patched
