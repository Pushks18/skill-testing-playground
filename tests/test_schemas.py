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


def test_trajectory_features_construction():
    from eval.schemas import TrajectoryFeatures
    f = TrajectoryFeatures(
        task_id="t1", domain="ancillery", task_weight=1.5, skill_injected=True,
        n_tools_called=0, called_any_tool=False, first_tool_name=None,
        expected_first_tool="add_ancillary", first_tool_correct=False,
        n_wrong_tool_calls=0, n_repeated_tool_calls=0,
        n_calls_missing_required_params=0, param_match_rate=0.0,
        n_steps=1, step_delta_vs_no_skill=-1,
        ended_without_tool_on_tool_task=True, looped_without_completion=False,
        output_is_verbal_only=True, verifier_score=0.0, delta_vs_no_skill=-1.0,
    )
    assert f.called_any_tool is False


def test_failure_classification_layer_literal():
    from eval.schemas import FailureClassification
    c = FailureClassification(
        task_id="t1", layer="harness:base_prompt", confidence=0.94,
        target_artifact="agent/harness_config.yaml::base_system_prompt",
        evidence={"called_any_tool": False},
    )
    assert c.layer == "harness:base_prompt"


def test_layer_cluster():
    from eval.schemas import LayerCluster
    cl = LayerCluster(
        layer="harness:base_prompt", domain="ancillery",
        task_ids=["t1", "t2"], dominant_failure_mode="NO_TOOL_CALL",
        target_artifact="agent/harness_config.yaml::base_system_prompt",
    )
    assert cl.n_failures == 2
