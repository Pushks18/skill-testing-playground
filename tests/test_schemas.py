from eval.schemas import EvalResult, ABResult, GateDecision, SkillCoverageMetrics


def test_ab_result_delta():
    no_skill = EvalResult(
        task_id="t1", domain="flight_search", skill_name=None,
        skill_version=None, score=0.5, steps=3, tools_called=[],
        tool_params={}, langsmith_run_id="r1", passed_verifier=True,
        judge_reasoning=None, latency_ms=100, tokens_used=200,
    )
    with_skill = EvalResult(
        task_id="t1", domain="flight_search", skill_name="flight-search",
        skill_version="v1.0", score=0.8, steps=2, tools_called=["search_flights"],
        tool_params={"origin": "JFK"}, langsmith_run_id="r2",
        passed_verifier=True, judge_reasoning=None, latency_ms=90, tokens_used=180,
    )
    ab = ABResult.from_pair("flight-search", no_skill, with_skill, task_weight=2.0)
    assert abs(ab.delta - 0.3) < 0.001
    assert ab.regression is False
    assert ab.step_delta == -1


def test_gate_decision_fields():
    d = GateDecision(
        verdict="BLOCK", tier=1, weighted_delta=-0.1,
        regression_rate=0.35, flagged_tasks=["t1"],
        langsmith_experiment_url="https://example.com",
        override_allowed=False,
    )
    assert d.override_allowed is False
