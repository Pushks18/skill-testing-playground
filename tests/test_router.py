# tests/test_router.py
import pathlib
import pytest

from eval.skill_router import RouteMatch
from agent.router import AgentRouter, FALLBACK_SKILL

SKILLS_ROOT = pathlib.Path("../travel-agent-skills/skills")


# ---------------------------------------------------------------------------
# Hermetic fixture: llm_tiebreak=False so real-router tests never hit LLM.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def router():
    return AgentRouter(SKILLS_ROOT, mock_mcp_url="http://localhost:8000",
                       llm_tiebreak=False)


def test_routes_obvious_domains(router):
    assert router.route_skill("Find me flights from JFK to LAX next Friday") == "flight-search"
    assert router.route_skill("I need a hotel in Paris for two nights") == "hotel-search"
    assert router.route_skill("My flight got cancelled, rebook me, ref BK1A2B3C") == "disruption-handling"


def test_low_confidence_falls_back_to_planning(router):
    assert router.route_skill("hmm") == FALLBACK_SKILL


def test_router_skips_nested_suite(router):
    # detection sub-suite has no top-level SKILL.md and must not be a route target
    assert "disruption-skill" not in router.available_skills()
    assert "flight-disruption-detection" not in router.available_skills()


def test_agent_cache_lazy_and_reused(router, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    a1 = router.agent_for("fare-rules")
    a2 = router.agent_for("fare-rules")
    assert a1 is a2


# ---------------------------------------------------------------------------
# New hybrid router tests (mock _router.rank via monkeypatch)
# ---------------------------------------------------------------------------

def _make_router_with_mocked_rank(monkeypatch, rank_results,
                                   llm_reply=None, llm_should_be_called=False):
    """Helper: build a hybrid AgentRouter, mock _router.rank, optionally mock openai."""
    r = AgentRouter(SKILLS_ROOT, mock_mcp_url="http://localhost:8000",
                    threshold=0.35, margin=0.05, llm_tiebreak=True)

    # Patch .rank on the internal _router instance
    monkeypatch.setattr(r._router, "rank", lambda text: rank_results)

    # Track whether openai was called
    call_log = []

    if llm_should_be_called is not None:
        class _FakeMsg:
            content = llm_reply or ""

        class _FakeChoice:
            message = _FakeMsg()

        class _FakeResp:
            choices = [_FakeChoice()]

        class _FakeCompletions:
            @staticmethod
            def create(**kw):
                call_log.append(kw)
                return _FakeResp()

        class _FakeChat:
            completions = _FakeCompletions()

        class _FakeClient:
            chat = _FakeChat()

        import openai
        monkeypatch.setattr(openai, "OpenAI", lambda **kw: _FakeClient())

    return r, call_log


def test_confident_case_no_llm_call(monkeypatch):
    """top1=0.6, top2=0.4 → gap=0.2 >= margin=0.05, score >= threshold → embedding path, no LLM."""
    rank_results = [
        RouteMatch(skill_name="flight-search", score=0.6, description="Finds flights"),
        RouteMatch(skill_name="hotel-search",  score=0.4, description="Finds hotels"),
        RouteMatch(skill_name="fare-rules",    score=0.2, description="Fare rules"),
    ]
    r, call_log = _make_router_with_mocked_rank(monkeypatch, rank_results,
                                                 llm_should_be_called=True)
    result = r.route_skill("Find me a flight to Paris")
    assert result == "flight-search"
    assert call_log == [], "LLM must NOT be called for confident routing"
    assert r.last_route_info["method"] == "embedding"


def test_hesitant_llm_valid_answer_used(monkeypatch):
    """top1=0.40, top2=0.38 → gap=0.02 < margin → hesitant → LLM called, valid answer used."""
    rank_results = [
        RouteMatch(skill_name="hotel-search",  score=0.40, description="Finds hotels"),
        RouteMatch(skill_name="flight-search", score=0.38, description="Finds flights"),
        RouteMatch(skill_name="fare-rules",    score=0.30, description="Fare rules"),
    ]
    r, call_log = _make_router_with_mocked_rank(monkeypatch, rank_results,
                                                 llm_reply="hotel-search",
                                                 llm_should_be_called=True)
    result = r.route_skill("I need somewhere to stay in Rome")
    assert result == "hotel-search"
    assert len(call_log) == 1, "LLM should have been called exactly once"
    assert r.last_route_info["method"] == "llm"


def test_llm_garbage_reply_falls_back_to_top1(monkeypatch):
    """LLM returns garbage → top1.score(0.40) >= threshold → top1 used."""
    rank_results = [
        RouteMatch(skill_name="flight-search", score=0.40, description="Finds flights"),
        RouteMatch(skill_name="hotel-search",  score=0.38, description="Finds hotels"),
        RouteMatch(skill_name="fare-rules",    score=0.30, description="Fare rules"),
    ]
    r, call_log = _make_router_with_mocked_rank(monkeypatch, rank_results,
                                                 llm_reply="BANANA!!!",
                                                 llm_should_be_called=True)
    result = r.route_skill("Book a ticket maybe?")
    assert result == "flight-search"
    assert len(call_log) == 1, "LLM was called but its garbage reply must be discarded"
    assert r.last_route_info["method"] == "fallback"


def test_llm_says_none_returns_planning_skill(monkeypatch):
    """LLM replies 'none' → FALLBACK_SKILL (planning-skill)."""
    rank_results = [
        RouteMatch(skill_name="flight-search", score=0.36, description="Finds flights"),
        RouteMatch(skill_name="hotel-search",  score=0.35, description="Finds hotels"),
        RouteMatch(skill_name="fare-rules",    score=0.30, description="Fare rules"),
    ]
    r, call_log = _make_router_with_mocked_rank(monkeypatch, rank_results,
                                                 llm_reply="none",
                                                 llm_should_be_called=True)
    result = r.route_skill("What is the meaning of life?")
    assert result == FALLBACK_SKILL
    assert len(call_log) == 1
    assert r.last_route_info["method"] == "llm"


def test_llm_tiebreak_false_never_calls_llm(monkeypatch):
    """llm_tiebreak=False → pure threshold path, LLM never called even in hesitant case."""
    r = AgentRouter(SKILLS_ROOT, mock_mcp_url="http://localhost:8000",
                    threshold=0.35, margin=0.05, llm_tiebreak=False)

    rank_results = [
        RouteMatch(skill_name="hotel-search",  score=0.40, description="Finds hotels"),
        RouteMatch(skill_name="flight-search", score=0.38, description="Finds flights"),
        RouteMatch(skill_name="fare-rules",    score=0.30, description="Fare rules"),
    ]
    # Even if we patch rank, the llm_tiebreak=False path never calls rank()
    # It calls self._router.route() instead. Patch that too so no real embedding.
    from eval.skill_router import RouteMatch as RM
    monkeypatch.setattr(r._router, "route",
                        lambda text, threshold=0.35: rank_results[0])

    call_log = []

    import openai
    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    call_log.append(kw)
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: _FakeClient())

    result = r.route_skill("I need a room in Tokyo")
    assert result == "hotel-search"
    assert call_log == [], "LLM must NEVER be called when llm_tiebreak=False"
    assert r.last_route_info["method"] == "embedding"


# ---------------------------------------------------------------------------
# Capability-safe policy (default): hesitant in-scope routes keep top1's
# skill but get the FULL toolset; below-threshold goes to planning. Never
# an LLM gamble. From the 2026-06-06 misroute diagnosis: the LLM tie-break
# was wrong on 23/64 decisions and caused 5 of the 10 fatal misroutes; a
# pure planning fallback fixed those but regressed correctly-routed
# thin-margin tasks by discarding their skill.
# ---------------------------------------------------------------------------

def test_default_policy_hesitant_keeps_skill_unscopes_tools(monkeypatch):
    """Hesitant in-scope: top1 skill chosen, scoped=False, LLM never called."""
    r = AgentRouter(SKILLS_ROOT, mock_mcp_url="http://localhost:8000")

    rank_results = [
        RouteMatch(skill_name="modify-booking", score=0.44, description="Modify bookings"),
        RouteMatch(skill_name="booking-skill",  score=0.39, description="Create bookings"),
    ]
    monkeypatch.setattr(r._router, "rank", lambda text: rank_results)

    call_log = []
    import openai
    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    call_log.append(kw)
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: _FakeClient())

    # gap = 0.05 < default margin 0.08 → hesitant → top1 skill, unscoped tools
    assert r.route_skill("Book flight FL101 for Jane Roe") == "modify-booking"
    assert call_log == [], "default policy must never call the LLM"
    assert r.last_route_info["method"] == "unscoped_specialist"
    assert r.last_route_info["scoped"] is False


def test_default_policy_below_threshold_falls_back_to_planning(monkeypatch):
    r = AgentRouter(SKILLS_ROOT, mock_mcp_url="http://localhost:8000")
    rank_results = [
        RouteMatch(skill_name="modify-booking", score=0.30, description="Modify bookings"),
        RouteMatch(skill_name="booking-skill",  score=0.28, description="Create bookings"),
    ]
    monkeypatch.setattr(r._router, "rank", lambda text: rank_results)
    assert r.route_skill("hmm") == FALLBACK_SKILL
    assert r.last_route_info["method"] == "margin_fallback"


def test_route_returns_unscoped_agent_for_hesitant(monkeypatch):
    """route() must build the hesitant specialist WITHOUT a tools_subset."""
    r = AgentRouter(SKILLS_ROOT, mock_mcp_url="http://localhost:8000")
    rank_results = [
        RouteMatch(skill_name="modify-booking", score=0.44, description="Modify bookings"),
        RouteMatch(skill_name="booking-skill",  score=0.39, description="Create bookings"),
    ]
    monkeypatch.setattr(r._router, "rank", lambda text: rank_results)

    built = {}
    import agent.router as ar

    def fake_build(skill_name, skills_root, mock_mcp_url, scoped=True):
        built["skill"] = skill_name
        built["scoped"] = scoped
        return object()

    monkeypatch.setattr(ar, "build_specialist_agent", fake_build)

    name, _agent = r.route("Book flight FL101 for Jane Roe")
    assert name == "modify-booking"
    assert built == {"skill": "modify-booking", "scoped": False}


def test_default_policy_confident_uses_specialist(monkeypatch):
    r = AgentRouter(SKILLS_ROOT, mock_mcp_url="http://localhost:8000")
    rank_results = [
        RouteMatch(skill_name="hotel-search",  score=0.60, description="Finds hotels"),
        RouteMatch(skill_name="flight-search", score=0.40, description="Finds flights"),
    ]
    monkeypatch.setattr(r._router, "rank", lambda text: rank_results)
    assert r.route_skill("Find me a hotel in Paris") == "hotel-search"
    assert r.last_route_info["method"] == "embedding"


def test_default_margin_is_008():
    r = AgentRouter(SKILLS_ROOT, mock_mcp_url="http://localhost:8000")
    assert r.margin == 0.08
