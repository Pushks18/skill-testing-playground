#!/usr/bin/env python
"""Update ../travel-agent-skills/docs/architecture.excalidraw with current facts.

Surgical text replacements (Langfuse→LangSmith, model defaults, gate
thresholds, skill list) plus a new "What's new 2026-06" section appended
below the existing canvas. Idempotent: skips edits already applied.
"""
from __future__ import annotations

import json
import pathlib

PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "travel-agent-skills" / "docs" / "architecture.excalidraw"

doc = json.loads(PATH.read_text())
elements = doc["elements"]


def replace_text(contains: str, new_text: str) -> bool:
    for el in elements:
        if el.get("type") == "text" and contains in el.get("text", ""):
            if el["text"] == new_text:
                return False
            el["text"] = new_text
            el["originalText"] = new_text
            el["version"] = el.get("version", 1) + 1
            lines = new_text.split("\n")
            size = el.get("fontSize", 14)
            el["width"] = max(len(l) for l in lines) * size * 0.6
            el["height"] = len(lines) * size * 1.25
            return True
    print(f"  !! no text element containing {contains!r}")
    return False


# 1. Langfuse → LangSmith
replace_text("Langfuse  (cloud.langfuse.com",
    "LangSmith  (smith.langchain.com)  — replaced Langfuse\n\n"
    "Full LLM call tree per run, tool spans\n"
    "Traces tagged: skill / condition / domain\n"
    "Trace URL stored in EvalResult\n"
    "→ surfaced in PR comment for regressions\n\n"
    "Keys: LANGSMITH_API_KEY / LANGSMITH_PROJECT\n"
    "⚠ monthly trace quota can hit 429 — disable via\n"
    "  LANGCHAIN_TRACING_V2=false")

# 2. CI secrets line
replace_text("Secrets: EVAL_PLATFORM_TOKEN",
    "Job 2: eval  (needs: validate)\n\n"
    "1. checkout skill-testing-playground @ main  (read-only)\n"
    "2. detect changed skill  (git diff HEAD^1)\n"
    "3. pip install -e .\n"
    "4. start mock MCP server &\n"
    "5. python -m eval.ab_compare \\\n"
    "     --skill-path <changed-skill> --trials 3\n"
    "6. post PR comment  (verdict + LangSmith trace links)\n\n"
    "Secrets: EVAL_PLATFORM_TOKEN  OPENROUTER_API_KEY\n"
    "         OPENAI_API_KEY  LANGSMITH_API_KEY")

# 3. Model footer
replace_text("OpenRouter  (openrouter.ai/api/v1)",
    "🔑  Models — eval default: gpt-4o-mini (OPENAI_API_KEY direct)\n"
    "Optimizer-side LLM: gpt-4o · others via OpenRouter (openrouter.ai/api/v1)\n\n"
    "Used by: Travel Agent · LLM Judge · Optimizer · propose_skill · skills generate · taskgen\n"
    "Per-model leaderboard: model recorded in every ab_results.json")

replace_text("Gemini 2.5 Flash (all LLM calls)",
    "gpt-4o-mini default · per --model")

# 4. Gate thresholds (recalibrated for N=3)
replace_text("T1 BLOCK    delta < -0.05",
    "Gate Check  (eval/gate_check.py)\n\n"
    "weighted_delta = Σ(delta × weight) / Σw\n"
    "Domain weights: booking=3.0 flight/hotel=2.0\n\n"
    "Thresholds calibrated for N=3 trials:\n"
    "T1 BLOCK   wΔ<−0.15 | crit<−0.30 | reg>50%  exit(1)\n"
    "T2 SOFT    wΔ<−0.05 | heavy<−0.20 | reg>35%  exit(1)\n"
    "T3 WARN    small regressions              exit(0)")

# 5. Travel agent model line
replace_text("Model: Gemini 2.5 Flash",
    "Travel Agent  (agent/travel_agent.py)\n"
    "LangGraph + LangChain\n\n"
    "system_prompt = harness_config base_system_prompt\n"
    "  + skill.body  (or no skill for baseline)\n"
    "harness_config.yaml externalized; HARNESS_CONFIG_PATH\n"
    "  env override for candidate configs\n\n"
    "Tools (9):\n"
    "  search_flights · search_hotels · create_booking\n"
    "  modify_booking · cancel_booking · get_fare_rules\n"
    "  check_availability · validate_passenger · get_itinerary\n\n"
    "Model: gpt-4o-mini (default) · --model for others\n"
    "agent_mode=orchestrated → Phase 8 specialists")

# 6. Skills list (9 skills)
replace_text("flight-search/SKILL.md",
    "flight-search/SKILL.md\nhotel-search/SKILL.md\nbooking-skill/SKILL.md\n"
    "fare-rules/SKILL.md\nmodify-booking/SKILL.md\nancillery-skill/SKILL.md\n"
    "planning-skill/SKILL.md\ndisruption-handling/SKILL.md\ndisruption-skill/SKILL.md\n\n"
    "registry.yaml\n  version, owners, status\n  tags, distribution\n\n"
    "releases/\n  ZIP artifacts\n  org-provisioned\n  manual upload")

# 7. GRPO box → current optimizer stack
replace_text("GRPO Optimizer  (eval/optimizer/)",
    "Optimizer Stack  (eval/optimizer/)\n\n"
    "optimize.py — two-target ReflACT trainer (Slice 3)\n"
    "  failure_classification.json → SKILL.md body OR one\n"
    "  harness_config key · 5:3:2 split · mixed gate\n"
    "  propose-only: *_proposed.* + optimization_report.json\n\n"
    "archive.py + bandit.py (Slice 4) — Thompson sampling\n"
    "  over 5 edit strategies (--explore)\n\n"
    "propose_skill.py — auto-PR for missing skills\n"
    "  branch proposal/<name> — NEVER auto-merged")

# 8. Append "What's new" section below existing canvas
NEW_SECTION_ID = "r_whatsnew_2026_06"
if not any(e["id"] == NEW_SECTION_ID for e in elements):
    max_y = max(e["y"] + e.get("height", 0) for e in elements)
    base_y = max_y + 60
    seed = max(e.get("seed", 0) for e in elements) + 1

    def el(id_, type_, x, y, w, h, **over):
        nonlocal_seed = over.pop("seed", None)
        d = {
            "id": id_, "type": type_, "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": "#0f172a", "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
            "roughness": 0, "opacity": 100, "roundness": None, "groupIds": [],
            "frameId": None, "boundElements": [], "seed": nonlocal_seed or seed,
            "version": 1, "versionNonce": 1, "isDeleted": False, "updated": 1,
            "link": None, "locked": False,
        }
        d.update(over)
        return d

    def txt(id_, x, y, content, size=13, color="#0f172a", family=3):
        lines = content.split("\n")
        return el(id_, "text", x, y,
                  max(len(l) for l in lines) * size * 0.6, len(lines) * size * 1.25,
                  strokeColor=color, text=content, fontSize=size, fontFamily=family,
                  textAlign="left", verticalAlign="top", baseline=int(size * 1.15),
                  containerId=None, originalText=content, lineHeight=1.25)

    new = [
        el(NEW_SECTION_ID, "rectangle", 20, base_y, 2720, 420,
           strokeColor="#7c3aed", backgroundColor="#f5f3ff", strokeWidth=3,
           roundness={"type": 3}),
        txt("t_whatsnew_h", 40, base_y + 12,
            "🆕  What's new (2026-06) — see skill-testing-playground/docs/architecture.excalidraw for the full pipeline",
            18, "#5b21b6", 2),
    ]
    cards = [
        ("Failure Classifier (Slice 1)",
         "classify_failures.py — rules-first\nlayer routing: skill:content vs\nharness:{base_prompt, tool_desc,\nnode_prompt} → clusters by\n(layer, domain) + confidence"),
        ("Harness Externalization (Slice 2)",
         "agent/harness_config.yaml:\nbase_system_prompt, tool_descriptions,\nnode_prompts + optimizable whitelist\nHARNESS_CONFIG_PATH env override"),
        ("Two-Target Optimizer (Slice 3)",
         "skillopt 0.1.0 ReflACTTrainer\nSKILL.md body OR one config key\n5:3:2 split · mixed gate · held-out\ntest is the honest number\npropose-only outputs"),
        ("Archive + Bandit (Slice 4)",
         "Thompson sampling over 5 edit\nstrategies: push-tool-action,\nbroaden-coverage, tighten-\nspecificity, add-edge-case, simplify"),
        ("Task Bank ×141 (9 domains)",
         "taskgen.py: LLM drafts → structural\n→ embedding dedupe → calibration\n→ human REVIEW.md → promote\n+ multi-turn user simulation"),
        ("Orchestrator (Phase 8)",
         "specialist agents w/ scoped tools,\nembedding+keyword hybrid router\n(passes accuracy gate);\nmono vs orch: mono wins −0.095"),
        ("Web Platform",
         "FastAPI skill_server :8080 ↔\nNext.js web/ :3000 (/skills /eval\n/observability) · SSE eval runs\nMonaco editor · per-model leaderboard"),
        ("Misc",
         "skill export → Claude Code format\ntrigger eval (60 cases)\nLangSmith tracer (Langfuse removed)\ngate thresholds recalibrated N=3"),
    ]
    cw, ch, gap = 640, 150, 30
    for i, (title, body) in enumerate(cards):
        col, row = i % 4, i // 4
        x = 40 + col * (cw + gap)
        y = base_y + 56 + row * (ch + gap)
        new.append(el(f"r_wn_{i}", "rectangle", x, y, cw, ch,
                      strokeColor="#7c3aed", backgroundColor="#ede9fe",
                      strokeWidth=2, roundness={"type": 3}, seed=seed + 10 + i))
        new.append(txt(f"t_wn_{i}_h", x + 12, y + 8, title, 13.5, "#5b21b6", 2))
        new.append(txt(f"t_wn_{i}_b", x + 12, y + 32, body, 11.5))
    elements.extend(new)
    print(f"  appended What's-new section ({len(new)} elements) at y={base_y}")

PATH.write_text(json.dumps(doc, indent=1))
print(f"updated {PATH} ({len(elements)} elements)")
