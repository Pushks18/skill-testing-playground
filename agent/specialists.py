# agent/specialists.py
"""Per-domain specialist agents: one skill always injected, tools scoped.

SKILL_TOOLS is deliberately conservative — unlisted skills (planning) get all
tools (tools_subset=None). The map is data; it can migrate into skill
frontmatter later.
"""
from __future__ import annotations

import pathlib

from agent.travel_agent import build_travel_agent
from eval.skill_loader import load_skill

SKILL_TOOLS: dict[str, list[str]] = {
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


def specialist_config(skill_name: str, skills_root: pathlib.Path) -> dict:
    """Resolve a specialist's skill body + tool subset. Raises if skill missing."""
    skill = load_skill(pathlib.Path(skills_root) / skill_name)
    if skill is None:
        raise FileNotFoundError(f"no SKILL.md for {skill_name!r} under {skills_root}")
    return {"skill_content": skill.body,
            "tools_subset": SKILL_TOOLS.get(skill_name)}


def build_specialist_agent(skill_name: str, skills_root: pathlib.Path,
                           mock_mcp_url: str = "http://localhost:8000"):
    cfg = specialist_config(skill_name, skills_root)
    return build_travel_agent(skill_content=cfg["skill_content"],
                              mock_mcp_url=mock_mcp_url,
                              tools_subset=cfg["tools_subset"])
