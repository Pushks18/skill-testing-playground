#!/usr/bin/env python
"""Generate docs/architecture.excalidraw for skill-testing-playground.

Deterministic: re-run after architecture changes and commit the output.
Element schema mirrors the hand-authored travel-agent-skills diagram
(rectangles + free text + simple arrows, roughness 0, solid fills).
"""
from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "architecture.excalidraw"

_seed = 0
_elements: list[dict] = []


def _next_seed() -> int:
    global _seed
    _seed += 1
    return _seed


def _base(id_: str, type_: str, x: float, y: float, w: float, h: float, **over) -> dict:
    el = {
        "id": id_, "type": type_, "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": "#1e293b", "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "roundness": None, "groupIds": [],
        "frameId": None, "boundElements": [], "seed": _next_seed(),
        "version": 1, "versionNonce": 1, "isDeleted": False, "updated": 1,
        "link": None, "locked": False,
    }
    el.update(over)
    return el


def rect(id_, x, y, w, h, stroke, fill, stroke_width=2):
    _elements.append(_base(
        id_, "rectangle", x, y, w, h,
        strokeColor=stroke, backgroundColor=fill, strokeWidth=stroke_width,
        roundness={"type": 3},
    ))


def text(id_, x, y, content, size=14, color="#1e293b", family=3):
    lines = content.split("\n")
    w = max(len(line) for line in lines) * size * 0.6
    h = len(lines) * size * 1.25
    _elements.append(_base(
        id_, "text", x, y, w, h,
        strokeColor=color, text=content, fontSize=size, fontFamily=family,
        textAlign="left", verticalAlign="top", baseline=int(size * 1.15),
        containerId=None, originalText=content, lineHeight=1.25,
    ))


def arrow(id_, x, y, dx, dy, color="#475569", dashed=False, label=None):
    _elements.append(_base(
        id_, "arrow", x, y, abs(dx), abs(dy),
        strokeColor=color, strokeWidth=2,
        strokeStyle="dashed" if dashed else "solid",
        roundness={"type": 2}, points=[[0, 0], [dx, dy]],
        lastCommittedPoint=None, startBinding=None, endBinding=None,
        startArrowhead=None, endArrowhead="arrow",
    ))
    if label:
        text(f"{id_}_lbl", x + min(0, dx) + 8, y + dy / 2 - 18, label, size=12,
             color=color, family=3)


def box(id_, x, y, w, h, title, body, stroke, fill, title_color=None):
    rect(f"r_{id_}", x, y, w, h, stroke, fill)
    text(f"t_{id_}_title", x + 14, y + 10, title, size=15,
         color=title_color or stroke, family=2)
    text(f"t_{id_}_body", x + 14, y + 38, body, size=12.5)


# ───────────────────────────── Section A: sources ───────────────────────────

rect("sec_a", 20, 20, 3120, 420, "#3b82f6", "#eff6ff", 3)
text("sec_a_h", 40, 32, "📦  SOURCES — skills, tasks, harness config", 19, "#1e40af", 2)

box("skills_repo", 40, 80, 700, 330,
    "travel-agent-skills  (../travel-agent-skills)",
    "skills/ + registry.yaml  (9 skills)\n"
    "  flight-search · hotel-search · booking-skill\n"
    "  fare-rules · modify-booking · ancillery-skill\n"
    "  planning-skill · disruption-handling · disruption-skill\n\n"
    "registry.yaml: version, owners, status, tags\n"
    "releases/: ZIP artifacts, org-provisioned\n\n"
    "CLI: skills create / generate / validate / package\n"
    "CI: PR to skills/** → validate → ab_compare gate",
    "#3b82f6", "#dbeafe")

box("task_bank", 780, 80, 760, 330,
    "Task Bank  (tasks/ — 141 tasks, 9 domains)",
    "booking-flow 20 · ancillery 20 · fare-rules 16\n"
    "edge-cases 16 · itinerary 16 · hotel-search 15\n"
    "flight-search 14 · disruption 12 · planning 12\n\n"
    "task.toml: domain, weight, skill=, [expected] tools,\n"
    "required_params, verifier  +  instruction.md\n\n"
    "taskgen (eval/taskgen.py): LLM drafts → gate 1 structural\n"
    "→ gate 2 embedding dedupe → gate 3 calibration\n"
    "→ tasks_drafts/<domain>/REVIEW.md (human) → promote",
    "#0d9488", "#ccfbf1")

box("harness_cfg", 1580, 80, 760, 330,
    "Harness Config  (agent/harness_config.yaml)",
    "Externalized, optimizable surface of the agent:\n"
    "  base_system_prompt\n"
    "  tool_descriptions (per tool)\n"
    "  node_prompts\n\n"
    "optimizable: whitelist — optimizer refuses other keys\n\n"
    "HARNESS_CONFIG_PATH env override (call-time):\n"
    "candidate configs evaluated without touching the\n"
    "real file; always restored via try/finally",
    "#9333ea", "#f3e8ff")

box("dyn_create", 2380, 80, 740, 330,
    "Dynamic Skill Creation",
    "PATH A — skills generate <name> --description ...\n"
    "  LLM drafts SKILL.md, registry status: draft,\n"
    "  human reviews → PR → CI eval gate\n\n"
    "PATH B — propose_skill (auto-proposal)\n"
    "  failure clusters (trajectory.db / ab_results)\n"
    "  → draft_skill_body() → open_skill_pr()\n"
    "  branch proposal/<name>, NEVER auto-merged\n\n"
    "Export: eval/export_skill.py → Claude Code format",
    "#d97706", "#fef3c7")

# ─────────────────────────── Section B: eval core ───────────────────────────

rect("sec_b", 20, 480, 3120, 560, "#16a34a", "#f0fdf4", 3)
text("sec_b_h", 40, 492, "🧪  EVAL CORE — the A/B loop", 19, "#166534", 2)

box("mock_mcp", 40, 540, 480, 220,
    "Mock MCP Server  :8000",
    "eval/mock_mcp/server.py\n"
    "9 travel endpoints (FastAPI)\n"
    "Deterministic — seeded by params\n\n"
    "Precondition for run_task,\n"
    "ab_compare, and the optimizer\n"
    "(driver preflights reachability)",
    "#16a34a", "#dcfce7")

box("agent", 560, 540, 620, 460,
    "Travel Agent  (agent/travel_agent.py)",
    "LangGraph + LangChain\n\n"
    "system_prompt = harness base_system_prompt\n"
    "  + skill.body (with_skill condition)\n\n"
    "Tools (9): search_flights · search_hotels\n"
    "  create_booking · modify_booking · cancel_booking\n"
    "  get_fare_rules · check_availability\n"
    "  validate_passenger · get_itinerary\n\n"
    "Models: gpt-4o-mini default (OPENAI_API_KEY);\n"
    "  others via OpenRouter (--model)\n\n"
    "agent_mode=orchestrated → Phase 8 router path",
    "#16a34a", "#dcfce7")

box("orchestrator", 1220, 540, 620, 460,
    "Orchestrator  (Phase 8)",
    "Specialist factory: per-domain agents with\n"
    "  scoped tools_subset + specialist cache\n\n"
    "AgentRouter: embedding router (all-MiniLM-L6-v2)\n"
    "  hybrid keyword+cosine — passes accuracy gate\n\n"
    "run_task(agent_mode=\"orchestrated\")\n"
    "  router → specialist → rollout\n\n"
    "orchestrator_compare.py: mono vs orchestrated\n"
    "  verdict so far: mono wins (Δ −0.095)\n\n"
    "Multi-turn user simulation for\n"
    "  clarifying-question tasks",
    "#0891b2", "#cffafe")

box("ab", 1880, 540, 620, 460,
    "A/B Harness  (eval/ab_compare.py)",
    "--skill-path <dir> --trials N --model <m>\n"
    "EVAL_TRIALS / EVAL_CONCURRENCY / EVAL_MODEL\n\n"
    "Task match: task.toml skill=\"name\" exact,\n"
    "  else SkillRouter semantic (cos ≥ 0.35)\n\n"
    "Per task × N trials:\n"
    "  A: no_skill baseline   B: with_skill\n"
    "  best-of-N per condition\n\n"
    "Verifiers: ToolCallVerifier (deterministic)\n"
    "  LLMJudgeVerifier (criteria, 3-run avg)\n\n"
    "→ results/<skill>_ab_results.json (model recorded)",
    "#16a34a", "#dcfce7")

box("gate", 2540, 540, 580, 220,
    "Gate Check  (eval/gate_check.py)",
    "weighted_delta = Σ(Δ·w)/Σw — booking 3.0,\n"
    "flight/hotel 2.0, disruption 2.0\n\n"
    "Thresholds calibrated for N=3 trials:\n"
    "  T1 BLOCK  wΔ<−0.15 | crit<−0.30 | reg>50%\n"
    "  T2 SOFT   wΔ<−0.05 | heavy<−0.20 | reg>35%\n"
    "  T3 WARN   small regressions   exit 0",
    "#dc2626", "#fee2e2")

box("cost", 2540, 790, 580, 210,
    "Cost + Latency  (eval/cost.py)",
    "Per run: tokens, cost_usd, latency_ms\n"
    "Per eval: total, avg/run, p95, deltas\n\n"
    "Pricing tables: OpenRouter strings +\n"
    "OpenAI-direct strings (gpt-4o, gpt-4o-mini,\n"
    "gpt-4.1*, o1-mini, o3-mini)",
    "#64748b", "#f1f5f9")

# ──────────────────── Section C: failure → optimization ─────────────────────

rect("sec_c", 20, 1080, 3120, 600, "#ea580c", "#fff7ed", 3)
text("sec_c_h", 40, 1092, "🔁  FAILURE → OPTIMIZATION LOOP (propose-only)", 19, "#9a3412", 2)

box("results", 40, 1140, 560, 240,
    "Results + Leaderboard",
    "results/<skill>_ab_results.json\n"
    "  verdict, tier, flagged_tasks,\n"
    "  regression_traces, per-task trials\n\n"
    "eval/leaderboard.py [--by-model]\n"
    "  per-(skill, model) rows",
    "#ea580c", "#ffedd5")

box("classifier", 640, 1140, 700, 380,
    "Failure Classifier  (eval/classify_failures.py)",
    "Rules-first, no LLM. Per failed task:\n"
    "TrajectoryFeatures → ordered layer rules\n\n"
    "Layers:\n"
    "  skill:content            → skills/<n>/SKILL.md\n"
    "  harness:base_prompt      → ::base_system_prompt\n"
    "  harness:tool_description → ::tool_descriptions\n"
    "  harness:node_prompt      → ::node_prompts\n\n"
    "Clusters by (layer, domain) with confidence\n"
    "→ failure_classification.json\n\n"
    "Qualify: harness n≥1, skill n≥2",
    "#ea580c", "#ffedd5")

box("optimizer", 1380, 1140, 880, 500,
    "Two-Target Optimizer  (eval/optimizer/optimize.py — Slice 3)",
    "python -m eval.optimizer.optimize [--cluster N] [--dry-run]\n"
    "  [--strategy ...] [--explore]\n\n"
    "TravelEnvAdapter + TravelTaskLoader plug run_task into\n"
    "skillopt 0.1.0 ReflACTTrainer (6-stage loop)\n"
    "  rollout = real eval vs mock MCP (gpt-4o-mini)\n"
    "  reflect/aggregate/select = gpt-4o\n"
    "  replacement prompts (wheel ships none)\n\n"
    "Targets:  skill → SKILL.md body (frontmatter preserved)\n"
    "          harness → ONE optimizable config key\n\n"
    "Deterministic 5:3:2 train/selection/test split\n"
    "Gate: mixed (never hard at ≤10-task scale)\n"
    "Held-out test evaluated once — the honest number\n"
    "No improvement on test → NO proposal written",
    "#9333ea", "#f3e8ff")

box("bandit", 2300, 1140, 820, 240,
    "Archive + Bandit  (Slice 4)",
    "eval/optimizer/{archive,bandit,variant_strategies}.py\n\n"
    "Strategies: push-tool-action · broaden-coverage ·\n"
    "  tighten-specificity · add-edge-case · simplify\n\n"
    "Thompson sampling over strategy arms (--explore);\n"
    "archive records outcomes per (target, strategy)",
    "#0891b2", "#cffafe")

box("proposals", 2300, 1410, 820, 240,
    "Proposed Outputs  (never auto-committed)",
    "eval/optimizer_output/<run>/\n"
    "  SKILL_proposed.md | harness_config_proposed.yaml\n"
    "  optimization_report.json — baseline vs best vs\n"
    "  held-out test, accepted/rejected edits, cost,\n"
    "  review checklist (run ab_compare on a 2nd skill\n"
    "  before merging any harness change)",
    "#dc2626", "#fee2e2")

# ───────────────── Section D: observability & serving ───────────────────────

rect("sec_d", 20, 1720, 3120, 480, "#475569", "#f8fafc", 3)
text("sec_d_h", 40, 1732, "📊  OBSERVABILITY & SERVING", 19, "#334155", 2)

box("langsmith", 40, 1780, 600, 240,
    "LangSmith  (tracer)",
    "Replaced Langfuse (dead path removed)\n\n"
    "Traces tagged: skill / condition / domain\n"
    "Trace URL stored in EvalResult\n\n"
    "Keys: LANGSMITH_API_KEY, LANGSMITH_PROJECT\n"
    "⚠ monthly trace quota can exhaust (429s) —\n"
    "  disable with LANGCHAIN_TRACING_V2=false",
    "#475569", "#e2e8f0")

box("trajdb", 680, 1780, 560, 240,
    "Trajectory Store  (trajectory.db)",
    "SQLite — runs + steps tables\n\n"
    "failure modes: NO_TOOL_CALL · WRONG_TOOL ·\n"
    "  MISSING_PARAM · MULTI_STEP_DROPOUT ·\n"
    "  PARTIAL_MATCH · HALLUCINATED_ID · UNKNOWN\n\n"
    "feeds classifier + propose_skill clustering",
    "#475569", "#e2e8f0")

box("backend", 1280, 1780, 620, 240,
    "FastAPI Backend  :8080  (skill_server.py)",
    ".venv/bin/uvicorn skill_server:app --port 8080\n\n"
    "/api/skills · /api/leaderboard · /api/models\n"
    "/api/eval/run (SSE stream of ab_compare)\n"
    "/api/trajectories · /api/skills/detect\n"
    "/api/optimizer-runs · /api/observability/links",
    "#3b82f6", "#dbeafe")

box("webui", 1940, 1780, 580, 240,
    "Next.js Web UI  :3000  (web/)",
    "npm run dev  (proxies /api/* → :8080)\n\n"
    "pages: /  /skills  /skills/[name]\n"
    "       /eval  /observability\n\n"
    "Monaco editor · recharts · Tailwind 4\n"
    "Legacy: streamlit run ui/app.py",
    "#0d9488", "#ccfbf1")

box("trigger", 2560, 1780, 560, 240,
    "Trigger Eval  (eval/trigger_eval.py)",
    "60-case trigger dataset (trigger/)\n"
    "Does the right skill activate for a\n"
    "given user utterance?\n\n"
    "SkillRouter accuracy measurement,\n"
    "legacy skill mappings fixed",
    "#d97706", "#fef3c7")

# ───────────────────────────────── arrows ───────────────────────────────────

arrow("a_skills_ab", 740, 410, 1300, 130, "#3b82f6", label="skill under test")
arrow("a_tasks_ab", 1540, 410, 560, 130, "#0d9488", label="tasks (domain match)")
arrow("a_cfg_agent", 1960, 410, -1000, 130, "#9333ea", label="config (env-overridable)")
arrow("a_ab_agent", 1880, 770, -40, 0, "#16a34a", label="run_task × 2 cond × N")
arrow("a_agent_mcp", 560, 650, -40, 0, "#16a34a", label="tool calls")
arrow("a_agent_orch", 1180, 770, 40, 0, "#0891b2", dashed=True, label="agent_mode=orchestrated")
arrow("a_ab_gate", 2500, 650, 40, 0, "#dc2626", label="verdict")
arrow("a_ab_results", 320, 1040, 0, 100, "#ea580c", label="ab_results.json")
arrow("a_results_clf", 600, 1260, 40, 0, "#ea580c")
arrow("a_clf_opt", 1340, 1330, 40, 0, "#ea580c", label="clusters")
arrow("a_bandit_opt", 2300, 1260, -40, 0, "#0891b2", label="strategy")
arrow("a_opt_prop", 2260, 1520, 40, 0, "#dc2626", label="improved on test only")
arrow("a_prop_pr", 2710, 1410, 0, -1000, "#d97706", dashed=True, label="human review → PR")
arrow("a_agent_ls", 340, 1680, 0, 100, "#475569", dashed=True, label="traces")
arrow("a_ab_traj", 960, 1680, 0, 100, "#475569", dashed=True, label="runs/steps")
arrow("a_be_web", 1900, 1900, 40, 0, "#3b82f6", label="/api/*")
arrow("a_results_be", 1590, 1680, 0, 100, "#3b82f6", dashed=True, label="results/ + optimizer_output/")

# ───────────────────────────────── title ────────────────────────────────────

text("title", 20, -40,
     "skill-testing-playground — architecture (2026-06-06) · generated by scripts/gen_architecture_diagram.py",
     16, "#0f172a", 2)

doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "scripts/gen_architecture_diagram.py",
    "elements": _elements,
    "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
    "files": {},
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, indent=1))
print(f"wrote {OUT} ({len(_elements)} elements)")
