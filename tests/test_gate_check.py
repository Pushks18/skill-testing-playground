# tests/test_gate_check.py
import pytest
from eval.schemas import ABResult, EvalResult, GateDecision
from eval.gate_check import gate_check, compute_weighted_delta

def make_ab(task_id, domain, delta, weight=1.0) -> ABResult:
    base = EvalResult(task_id=task_id, domain=domain, skill_name="test",
                      skill_version="v1", score=0.5, steps=2, tools_called=[],
                      tool_params={}, langsmith_run_id="", passed_verifier=True,
                      judge_reasoning=None, latency_ms=100, tokens_used=100)
    with_s = EvalResult(task_id=task_id, domain=domain, skill_name="test",
                        skill_version="v1", score=0.5 + delta, steps=2, tools_called=[],
                        tool_params={}, langsmith_run_id="", passed_verifier=True,
                        judge_reasoning=None, latency_ms=100, tokens_used=100)
    return ABResult.from_pair("test", base, with_s, task_weight=weight)

def test_pass():
    results = [make_ab(f"t{i}", "flight_search", 0.1, 2.0) for i in range(5)]
    d = gate_check(results)
    assert d.verdict == "PASS"
    assert d.tier == 0

def test_tier1_hard_block_on_negative_weighted_delta():
    results = [make_ab(f"t{i}", "flight_search", -0.1, 2.0) for i in range(5)]
    d = gate_check(results)
    assert d.verdict == "BLOCK"
    assert d.tier == 1
    assert d.override_allowed is False

def test_tier1_booking_flow_critical():
    results = [make_ab("book1", "booking_flow", -0.20, 3.0)]
    results += [make_ab(f"t{i}", "flight_search", 0.1, 2.0) for i in range(4)]
    d = gate_check(results)
    assert d.verdict == "BLOCK"
    assert d.tier == 1

def test_tier2_soft_block():
    results = [make_ab(f"t{i}", "flight_search", -0.02, 2.0) for i in range(3)]
    results += [make_ab(f"t{i+3}", "flight_search", 0.05, 2.0) for i in range(2)]
    d = gate_check(results)
    assert d.verdict in ("SOFT_BLOCK", "WARN", "BLOCK")

def test_tier3_warn():
    results = [make_ab("t1", "flight_search", -0.02, 1.0)]
    results += [make_ab(f"t{i+2}", "flight_search", 0.15, 1.0) for i in range(9)]
    d = gate_check(results)
    assert d.verdict in ("WARN", "PASS")

def test_regression_rate_block():
    results = [make_ab(f"t{i}", "flight_search", -0.01, 1.0) for i in range(4)]
    results += [make_ab(f"t{i+4}", "flight_search", 0.1, 1.0) for i in range(6)]
    d = gate_check(results)
    assert d.verdict == "BLOCK"

def test_compute_weighted_delta():
    results = [make_ab("t1", "flight_search", 0.1, 2.0),
               make_ab("t2", "booking_flow", 0.2, 3.0)]
    from eval.gate_check import TASK_WEIGHTS
    wd = compute_weighted_delta(results, TASK_WEIGHTS)
    expected = (0.1 * 2.0 + 0.2 * 3.0) / (2.0 + 3.0)
    assert abs(wd - expected) < 0.001
