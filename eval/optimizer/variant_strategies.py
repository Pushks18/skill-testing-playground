# eval/optimizer/variant_strategies.py

STRATEGIES = {
    "variant_1_tighten_triggers": """
Rewrite the "When to Use" section of this skill to be more specific and restrictive.
The current skill is triggering on requests it shouldn't handle (low precision).
Add 2-3 explicit "Do NOT use when:" conditions. Keep the workflow section unchanged.
""",
    "variant_2_broaden_triggers": """
Expand the "When to Use" section to cover more related request patterns.
The skill is missing relevant requests (low recall).
Add 3-4 additional trigger examples. Look at the failing tasks for patterns.
""",
    "variant_3_edge_case_handling": """
Add an "Edge Cases" section to the skill documenting the specific failure patterns
from the failing traces. Add explicit handling steps for each edge case.
Keep trigger conditions unchanged.
""",
    "variant_4_focused_modules": """
Reduce this skill to its 2-3 most essential modules only.
Cut any step not directly required for the core use case.
SkillsBench shows focused 2-3 module skills outperform comprehensive ones.
""",
    "variant_5_restructure_workflow": """
Reorder the Workflow section based on what the failing traces show the agent
actually needs to do first. Move the most commonly needed step to position 1.
Do not change the content of any step, only the order.
""",
}


def get_strategy_prompt(strategy_key: str, skill_content: str, failing_traces) -> str:
    base = STRATEGIES.get(strategy_key, STRATEGIES["variant_4_focused_modules"])
    traces_summary = "\n".join(f"- {t}" for t in failing_traces[:5])
    return f"""You are improving a travel agent skill document.

Current SKILL.md:
{skill_content}

Failing task summaries:
{traces_summary}

Instruction:
{base}

Output ONLY the improved SKILL.md content. No explanations, no markdown fences."""
