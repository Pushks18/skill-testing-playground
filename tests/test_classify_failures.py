# tests/test_classify_failures.py
import pytest
from eval.classify_failures import extract_features, load_expected, classify_layer


def ab_task(task_id, ws_tools, ws_params, ws_score, ws_passed, ws_steps,
            ns_score=1.0, ns_passed=True, ns_steps=2, domain="ancillery", weight=1.5):
    """Build an ab_results.json task entry (dict shape, as JSON round-trips it)."""
    return {
        "skill_name": "ancillery-skill",
        "task_id": task_id,
        "domain": domain,
        "task_weight": weight,
        "no_skill": {
            "task_id": task_id, "domain": domain, "score": ns_score,
            "steps": ns_steps, "tools_called": ["add_ancillary"],
            "tool_params": {"add_ancillary": {"booking_id": "BK1"}},
            "passed_verifier": ns_passed,
        },
        "with_skill": {
            "task_id": task_id, "domain": domain, "score": ws_score,
            "steps": ws_steps, "tools_called": ws_tools,
            "tool_params": ws_params, "passed_verifier": ws_passed,
        },
        "delta": ws_score - ns_score,
        "step_delta": ws_steps - ns_steps,
    }


EXPECTED = {"tools": ["add_ancillary"], "required_params": {}}


def test_features_no_tool_call():
    """ancillery-002/006 signature: with_skill called zero tools."""
    t = ab_task("ancillery-002", [], {}, ws_score=0.0, ws_passed=False, ws_steps=1)
    f = extract_features(t, EXPECTED)
    assert f.called_any_tool is False
    assert f.output_is_verbal_only is True
    assert f.ended_without_tool_on_tool_task is True
    assert f.delta_vs_no_skill == -1.0
    assert f.skill_injected is True


def test_features_wrong_tools_extra_steps():
    """ancillery-003 signature: verification tools called, required tool never reached."""
    t = ab_task(
        "ancillery-003",
        ["get_itinerary", "get_fare_rules"],
        {"get_itinerary": {"booking_id": "BK9"}, "get_fare_rules": {"flight_id": "BK9"}},
        ws_score=0.0, ws_passed=False, ws_steps=3,
    )
    f = extract_features(t, EXPECTED)
    assert f.called_any_tool is True
    assert f.first_tool_name == "get_itinerary"
    assert f.first_tool_correct is False
    assert f.n_wrong_tool_calls == 2
    assert f.ended_without_tool_on_tool_task is True
    assert f.step_delta_vs_no_skill == 1
    # No required_params defined → param features stay neutral
    assert f.param_match_rate == 1.0


def test_features_correct_tool_missing_param():
    """skill:content signature: right tool, bad params."""
    t = ab_task(
        "x-001", ["add_ancillary"], {"add_ancillary": {"booking_id": "BK1"}},
        ws_score=0.4, ws_passed=False, ws_steps=2,
    )
    expected = {"tools": ["add_ancillary"],
                "required_params": {"add_ancillary": ["booking_id", "service_type"]}}
    f = extract_features(t, expected)
    assert f.first_tool_correct is True
    assert f.n_calls_missing_required_params == 1
    assert f.param_match_rate == 0.5
    assert f.ended_without_tool_on_tool_task is False


def test_features_repeated_calls_mark_loop():
    t = ab_task(
        "x-002", ["get_itinerary", "get_itinerary", "get_itinerary"],
        {"get_itinerary": {"booking_id": "BK1"}},
        ws_score=0.0, ws_passed=False, ws_steps=4,
    )
    f = extract_features(t, EXPECTED)
    assert f.n_repeated_tool_calls == 2
    assert f.looped_without_completion is True


def test_load_expected_reads_task_toml(tmp_path):
    task_dir = tmp_path / "ancillery-099"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        '[task]\nid = "ancillery-099"\ndomain = "ancillery"\n'
        'skill = "ancillery-skill"\nverifier = "tool_call_check"\nweight = 1.5\n\n'
        '[expected]\ntools = ["add_ancillary"]\n'
    )
    exp = load_expected(task_dir)
    assert exp["tools"] == ["add_ancillary"]
    assert exp["required_params"] == {}


def test_features_required_tool_never_called_zeroes_param_rate():
    """Wrong tool called while the required tool has required params → params unmet."""
    t = ab_task(
        "x-003", ["search_hotels"], {"search_hotels": {"location": "LA"}},
        ws_score=0.0, ws_passed=False, ws_steps=2,
    )
    expected = {"tools": ["add_ancillary"],
                "required_params": {"add_ancillary": ["booking_id", "service_type"]}}
    f = extract_features(t, expected)
    assert f.param_match_rate == 0.0
    assert f.n_calls_missing_required_params == 1
    assert f.ended_without_tool_on_tool_task is True


def test_features_correct_tool_no_params_recorded():
    """Correct tool called but tool_params has no entry for it."""
    t = ab_task(
        "x-004", ["add_ancillary"], {},
        ws_score=0.0, ws_passed=False, ws_steps=2,
    )
    expected = {"tools": ["add_ancillary"],
                "required_params": {"add_ancillary": ["booking_id"]}}
    f = extract_features(t, expected)
    assert f.param_match_rate == 0.0
    assert f.n_calls_missing_required_params == 1


def _classify(t, expected=EXPECTED):
    f = extract_features(t, expected)
    no_skill_passed = t["no_skill"]["passed_verifier"]
    return classify_layer(f, no_skill_passed=no_skill_passed, skill_name=t["skill_name"])


def test_classify_002_no_tool_call_is_base_prompt():
    """The thesis check: verbal-only failure routes to harness, never skill."""
    t = ab_task("ancillery-002", [], {}, ws_score=0.0, ws_passed=False, ws_steps=1)
    c = _classify(t)
    assert c.layer == "harness:base_prompt"
    assert c.confidence >= 0.9
    assert c.target_artifact == "agent/harness_config.yaml::base_system_prompt"
    # no_skill passed + delta -1.0 → over-prescription is a competing signal, recorded
    assert "competing_layer" in c.evidence


def test_classify_003_verification_derail_is_node_prompt():
    """Rule 2 compound arm: multi-tool spiral, required tool never reached."""
    t = ab_task(
        "ancillery-003",
        ["get_itinerary", "get_fare_rules"],
        {"get_itinerary": {"booking_id": "BK9"}, "get_fare_rules": {"flight_id": "BK9"}},
        ws_score=0.0, ws_passed=False, ws_steps=3,
    )
    c = _classify(t)
    assert c.layer == "harness:node_prompt"
    assert c.target_artifact == "agent/harness_config.yaml::node_prompts"


def test_classify_single_wrong_tool_is_tool_description():
    t = ab_task(
        "x-003", ["search_hotels"], {"search_hotels": {"location": "LA"}},
        ws_score=0.0, ws_passed=False, ws_steps=2,
        ns_score=0.5, ns_passed=False,  # also fails no_skill → not over-prescription
    )
    c = _classify(t)
    assert c.layer == "harness:tool_description"


def test_classify_missing_param_is_skill_content():
    t = ab_task(
        "x-004", ["add_ancillary"], {"add_ancillary": {"booking_id": "BK1"}},
        ws_score=0.4, ws_passed=False, ws_steps=2,
        ns_score=0.6, ns_passed=False,
    )
    expected = {"tools": ["add_ancillary"],
                "required_params": {"add_ancillary": ["booking_id", "service_type"]}}
    c = _classify(t, expected)
    assert c.layer == "skill:content"
    assert c.target_artifact == "skills/ancillery-skill/SKILL.md"


def test_classify_right_tool_full_params_only_with_skill_fails_is_over_prescription():
    """Right tool, right params, but only the with_skill condition fails badly."""
    t = ab_task(
        "x-005", ["add_ancillary"],
        {"add_ancillary": {"booking_id": "BK1", "service_type": "meal_selection"}},
        ws_score=0.0, ws_passed=False, ws_steps=2,
    )
    expected = {"tools": ["add_ancillary"],
                "required_params": {"add_ancillary": ["booking_id", "service_type"]}}
    c = _classify(t, expected)
    assert c.layer == "skill:over_prescription"


def test_classify_unexplained_failure_falls_back_to_skill_content():
    """Rule 6 fallback: right tool, full params, both conditions fail → low-confidence skill:content."""
    t = ab_task(
        "x-006", ["add_ancillary"],
        {"add_ancillary": {"booking_id": "BK1", "service_type": "meal_selection"}},
        ws_score=0.3, ws_passed=False, ws_steps=2,
        ns_score=0.4, ns_passed=False,  # no_skill also failed → no over-prescription signal
    )
    expected = {"tools": ["add_ancillary"],
                "required_params": {"add_ancillary": ["booking_id", "service_type"]}}
    c = _classify(t, expected)
    assert c.layer == "skill:content"
    assert c.confidence == 0.50
