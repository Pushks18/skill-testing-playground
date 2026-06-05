# agent/router.py
"""Phase 8 orchestrator: embedding router → per-domain specialist agents.

Route ONCE per conversation (multi-turn affinity is the caller's job: keep
using the returned agent). Below-threshold matches fall back to the planning
specialist, which keeps all tools.
"""
from __future__ import annotations

import pathlib

from eval.skill_router import SkillRouter
from agent.specialists import build_specialist_agent

FALLBACK_SKILL = "planning-skill"
ROUTE_THRESHOLD = 0.35


class AgentRouter:
    def __init__(self, skills_root: pathlib.Path,
                 mock_mcp_url: str = "http://localhost:8000",
                 threshold: float = ROUTE_THRESHOLD):
        self.skills_root = pathlib.Path(skills_root)
        self.mock_mcp_url = mock_mcp_url
        self.threshold = threshold
        self._router = SkillRouter.from_skill_dir(self.skills_root)
        self._agents: dict[str, object] = {}

    def available_skills(self) -> list[str]:
        return self._router.available()

    def route_skill(self, text: str) -> str:
        match = self._router.route(text, threshold=self.threshold)
        return match.skill_name if match else FALLBACK_SKILL

    def agent_for(self, skill_name: str):
        if skill_name not in self._agents:
            self._agents[skill_name] = build_specialist_agent(
                skill_name, self.skills_root, self.mock_mcp_url)
        return self._agents[skill_name]

    def route(self, text: str):
        """(skill_name, agent) for a new conversation."""
        name = self.route_skill(text)
        return name, self.agent_for(name)
