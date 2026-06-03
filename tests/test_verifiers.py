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
