# agent/router.py
"""Phase 8 orchestrator: embedding router → per-domain specialist agents.

Route ONCE per conversation (multi-turn affinity is the caller's job: keep
using the returned agent). Below-threshold matches fall back to the planning
specialist, which keeps all tools.

Margin-gated routing with safe fallback (Phase 8.1):
- CONFIDENT: top1.score >= threshold AND (top1.score - top2.score) >= margin
  → use embedding result directly (no LLM).
- HESITANT: route to the planning specialist (all tools). A wrong scoped
  specialist is fatal when the needed tool is outside its subset; planning
  is never fatal. (2026-06-06 diagnosis: 10 fatal misroutes — 5 from the
  LLM tie-break, which was wrong on 23/64 decisions, 4 from thin-margin
  embedding wins. margin=0.08 + fallback leaves 1.)

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
            # CONFIDENT — embedding result is good enough
            self.last_route_info = {
                "method": "embedding",
                "top": [(r.skill_name, r.score) for r in ranked[:3]],
            }
            return top1.skill_name

        if self.llm_tiebreak:
            # Legacy hybrid: gamble on a gpt-4o-mini tie-break
            return self._llm_tiebreak(text, ranked)

        # HESITANT (default policy) — commit only when confident; the planning
        # specialist keeps all tools, so a soft route is never fatal.
        self.last_route_info = {
            "method": "margin_fallback",
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

    def agent_for(self, skill_name: str):
        if skill_name not in self._agents:
            self._agents[skill_name] = build_specialist_agent(
                skill_name, self.skills_root, self.mock_mcp_url)
        return self._agents[skill_name]

    def route(self, text: str):
        """(skill_name, agent) for a new conversation."""
        name = self.route_skill(text)
        return name, self.agent_for(name)
