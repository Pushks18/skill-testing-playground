# agent/router.py
"""Phase 8 orchestrator: embedding router → per-domain specialist agents.

Route ONCE per conversation (multi-turn affinity is the caller's job: keep
using the returned agent). Below-threshold matches fall back to the planning
specialist, which keeps all tools.

Margin-gated routing with capability-safe fallback (Phase 8.2):
- CONFIDENT (top1 >= threshold AND margin >= 0.08): scoped specialist.
- HESITANT (top1 >= threshold, thin margin): top1's skill with the FULL
  toolset. Fatality comes from tool scoping, not routing — a wrong skill
  with all tools is recoverable, a right skill missing its tool is not.
- OUT OF SCOPE (top1 < threshold): planning specialist (all tools).

Evidence (2026-06-06): 10 fatal misroutes — 5 from the LLM tie-break (wrong
on 23/64 decisions), 4 from thin-margin embedding wins. A pure planning
fallback fixed all 10 but regressed correctly-routed thin-margin tasks
(disruption/fare-rules 1.00→0.00) by discarding their skill; keeping the
skill and unscoping tools retains both halves.

Legacy policies, selectable per constructor arg:
- llm_tiebreak=True  → hesitant cases call a gpt-4o-mini tie-break.
- llm_tiebreak=False → pure threshold behavior (no margin gate, no LLM).
"""
from __future__ import annotations

import os
import pathlib

from dotenv import load_dotenv
load_dotenv()

from eval.skill_router import SkillRouter
from agent.specialists import build_specialist_agent

FALLBACK_SKILL = "planning-skill"
ROUTE_THRESHOLD = 0.35
_DEFAULT_MARGIN = 0.08


class AgentRouter:
    def __init__(self, skills_root: pathlib.Path,
                 mock_mcp_url: str = "http://localhost:8000",
                 threshold: float = ROUTE_THRESHOLD,
                 margin: float = _DEFAULT_MARGIN,
                 llm_tiebreak: bool | None = None):
        self.skills_root = pathlib.Path(skills_root)
        self.mock_mcp_url = mock_mcp_url
        self.threshold = threshold
        self.margin = margin
        self.llm_tiebreak = llm_tiebreak
        self._router = SkillRouter.from_skill_dir(self.skills_root)
        self._agents: dict[str, object] = {}
        # Set after every route_skill() call; callers can inspect for reporting
        self.last_route_info: dict = {}

    def available_skills(self) -> list[str]:
        return self._router.available()

    def route_skill(self, text: str) -> str:
        if self.llm_tiebreak is False:
            # Legacy pure-threshold behavior: top match or fallback, never LLM
            match = self._router.route(text, threshold=self.threshold)
            chosen = match.skill_name if match else FALLBACK_SKILL
            self.last_route_info = {
                "method": "embedding",
                "top": [(match.skill_name, match.score)] if match else [],
            }
            return chosen

        # --- Margin-gated path ---
        ranked = self._router.rank(text)

        if len(ranked) < 2:
            # Can't compute margin — fall back
            top = ranked[0] if ranked else None
            chosen = top.skill_name if (top and top.score >= self.threshold) else FALLBACK_SKILL
            self.last_route_info = {
                "method": "fallback",
                "top": [(r.skill_name, r.score) for r in ranked[:3]],
            }
            return chosen

        top1, top2 = ranked[0], ranked[1]
        gap = top1.score - top2.score

        if top1.score >= self.threshold and gap >= self.margin:
            # CONFIDENT — embedding result is good enough; tools stay scoped
            self.last_route_info = {
                "method": "embedding",
                "scoped": True,
                "top": [(r.skill_name, r.score) for r in ranked[:3]],
            }
            return top1.skill_name

        if self.llm_tiebreak:
            # Legacy hybrid: gamble on a gpt-4o-mini tie-break
            return self._llm_tiebreak(text, ranked)

        if top1.score >= self.threshold:
            # HESITANT but in-scope (default policy) — keep top1's SKILL but
            # grant the FULL toolset. Fatality comes from tool scoping, not
            # routing: a wrong skill with all tools is recoverable, a right
            # skill missing its tool is not. (2026-06-06 second comparison:
            # planning-fallback fixed all 10 fatal misroutes but threw away
            # the skill on correctly-routed thin-margin tasks — disruption
            # and fare-rules regressed 1.00→0.00. This keeps both.)
            self.last_route_info = {
                "method": "unscoped_specialist",
                "scoped": False,
                "top": [(r.skill_name, r.score) for r in ranked[:3]],
            }
            return top1.skill_name

        # OUT OF SCOPE — below threshold entirely: planning fallback
        self.last_route_info = {
            "method": "margin_fallback",
            "scoped": False,
            "top": [(r.skill_name, r.score) for r in ranked[:3]],
        }
        return FALLBACK_SKILL

    def _llm_tiebreak(self, text: str, ranked: list) -> str:
        """Ask gpt-4o-mini to choose among top-3 candidates."""
        import openai

        top3 = ranked[:3]
        candidates = [m.skill_name for m in top3]
        candidate_lines = "\n".join(
            f"{m.skill_name}: {m.description[:120]}" for m in top3
        )
        options_list = ", ".join(candidates) + ", none"

        system_prompt = (
            "You are a travel-agent skill router. The available skills are:\n"
            f"{candidate_lines}\n\n"
            f"Also available: none (if the request does not match any skill).\n"
            f"Reply with exactly one skill name from this list: {options_list}."
        )
        user_prompt = text

        api_key = os.environ.get("OPENAI_API_KEY")
        client = openai.OpenAI(api_key=api_key)
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=20,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            reply = resp.choices[0].message.content.strip().lower()
        except Exception:
            reply = ""

        self.last_route_info = {
            "method": "llm",
            "llm_reply": reply,
            "top": [(r.skill_name, r.score) for r in ranked[:3]],
        }

        # Strict parse: reply must exactly equal a candidate name or "none"
        if reply == "none":
            return FALLBACK_SKILL
        for name in candidates:
            if reply == name.lower():
                return name

        # LLM gave garbage — deterministic fallback
        top1 = ranked[0]
        self.last_route_info["method"] = "fallback"
        return top1.skill_name if top1.score >= self.threshold else FALLBACK_SKILL

    def agent_for(self, skill_name: str, scoped: bool = True):
        key = (skill_name, scoped)
        if key not in self._agents:
            self._agents[key] = build_specialist_agent(
                skill_name, self.skills_root, self.mock_mcp_url, scoped=scoped)
        return self._agents[key]

    def route(self, text: str):
        """(skill_name, agent) for a new conversation."""
        name = self.route_skill(text)
        scoped = self.last_route_info.get("scoped", True)
        return name, self.agent_for(name, scoped=scoped)
