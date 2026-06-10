# tests/test_verifiers.py
import pytest
from eval.verifiers.tool_call import ToolCallVerifier

def test_tool_call_verifier_pass():
    v = ToolCallVerifier(
        required_tools=["search_flights"],
        required_params={"search_flights": ["origin", "destination", "date"]},
    )
    result = v.verify(
        agent_output={"response": "Found 3 flights", "tools_called": [
            {"name": "search_flights", "params": {"origin": "JFK", "destination": "LAX", "date": "2026-07-01"}}
        ]}
    )
    assert result.passed is True
    assert result.score == 1.0

def test_tool_call_verifier_missing_tool():
    v = ToolCallVerifier(
        required_tools=["search_flights"],
        required_params={"search_flights": ["origin"]},
    )
    result = v.verify(agent_output={"response": "I searched", "tools_called": []})
    assert result.passed is False
    assert result.score == 0.0
    assert "search_flights" in result.reason

def test_tool_call_verifier_missing_param():
    v = ToolCallVerifier(
        required_tools=["search_flights"],
        required_params={"search_flights": ["origin", "destination", "date"]},
    )
    result = v.verify(agent_output={"response": "ok", "tools_called": [
        {"name": "search_flights", "params": {"origin": "JFK"}}
    ]})
    assert result.passed is False
    assert result.score < 1.0

def test_tool_call_verifier_multiple_tools():
    v = ToolCallVerifier(
        required_tools=["check_availability", "create_booking"],
        required_params={
            "check_availability": ["resource_id", "date"],
            "create_booking": ["flight_id", "passenger"],
        },
    )
    result = v.verify(agent_output={"response": "booked", "tools_called": [
        {"name": "check_availability", "params": {"resource_id": "FL123", "date": "2026-07-01"}},
        {"name": "create_booking", "params": {"flight_id": "FL123", "passenger": {"name": "Alice"}}},
    ]})
    assert result.passed is True
    assert result.score == 1.0


# ── LLMJudgeVerifier robustness (judge errors must not score as 0.0) ─────────

from eval.verifiers.llm_judge import LLMJudgeVerifier, _parse_judge_output


def test_parse_judge_output_clean():
    score, reasoning = _parse_judge_output('{"score": 0.75, "reasoning": "good"}')
    assert score == 0.75 and reasoning == "good"


def test_parse_judge_output_fenced():
    score, _ = _parse_judge_output('```json\n{"score": 1.0, "reasoning": "ok"}\n```')
    assert score == 1.0


def test_parse_judge_output_truncated_salvages_score():
    # completion cap cut the reasoning mid-string — score field still recoverable
    score, reasoning = _parse_judge_output('{"score": 0.5, "reasoning": "the agent did')
    assert score == 0.5
    assert "truncated" in reasoning


def test_parse_judge_output_unparseable_raises():
    with pytest.raises(ValueError):
        _parse_judge_output("I think it deserves a high score")


def test_judge_errors_excluded_from_average(monkeypatch):
    v = LLMJudgeVerifier(instruction="task", runs=3)
    outcomes = iter([
        ValueError("boom"), ValueError("boom"),  # run 1: fails + retry fails -> excluded
        (1.0, "great"),                           # run 2
        (1.0, "great"),                           # run 3
    ])

    def fake_judge(response):
        o = next(outcomes)
        if isinstance(o, Exception):
            raise o
        return o

    monkeypatch.setattr(v, "_judge_once", fake_judge)
    result = v.verify({"response": "hi"})
    assert result.score == 1.0          # errored run did not drag the mean to 0.67
    assert result.passed is True
    assert "1 errored run(s) excluded" in result.reason


def test_judge_retry_recovers(monkeypatch):
    v = LLMJudgeVerifier(instruction="task", runs=1)
    outcomes = iter([ValueError("transient"), (0.75, "fine")])

    def fake_judge(response):
        o = next(outcomes)
        if isinstance(o, Exception):
            raise o
        return o

    monkeypatch.setattr(v, "_judge_once", fake_judge)
    result = v.verify({"response": "hi"})
    assert result.score == 0.75


def test_judge_all_runs_failing_flags_infra(monkeypatch):
    v = LLMJudgeVerifier(instruction="task", runs=2)

    def always_fail(response):
        raise ValueError("api down")

    monkeypatch.setattr(v, "_judge_once", always_fail)
    result = v.verify({"response": "hi"})
    assert result.passed is False
    assert "JUDGE_INFRA_FAILURE" in result.reason
