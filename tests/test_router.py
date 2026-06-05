# tests/test_router.py
import pathlib
import pytest

from agent.router import AgentRouter

SKILLS_ROOT = pathlib.Path("../travel-agent-skills/skills")


@pytest.fixture(scope="module")
def router():
    return AgentRouter(SKILLS_ROOT, mock_mcp_url="http://localhost:8000")


def test_routes_obvious_domains(router):
    assert router.route_skill("Find me flights from JFK to LAX next Friday") == "flight-search"
    assert router.route_skill("I need a hotel in Paris for two nights") == "hotel-search"
    assert router.route_skill("My flight got cancelled, rebook me, ref BK1A2B3C") == "disruption-handling"


def test_low_confidence_falls_back_to_planning(router):
    assert router.route_skill("hmm") == "planning-skill"


def test_router_skips_nested_suite(router):
    # detection sub-suite has no top-level SKILL.md and must not be a route target
    assert "disruption-skill" not in router.available_skills()
    assert "flight-disruption-detection" not in router.available_skills()


def test_agent_cache_lazy_and_reused(router, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    a1 = router.agent_for("fare-rules")
    a2 = router.agent_for("fare-rules")
    assert a1 is a2
