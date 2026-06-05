# tests/test_orchestrator_compare.py
from eval.orchestrator_compare import router_accuracy, summarize_modes


def test_router_accuracy_counts():
    labels = [("find flights", "flight-search"), ("hotel in rome", "hotel-search"),
              ("hello", None)]
    routed = ["flight-search", "flight-search", "planning-skill"]
    rep = router_accuracy(labels, routed, fallback="planning-skill")
    fs = rep["per_skill"]["flight-search"]
    assert fs["tp"] == 1 and fs["fp"] == 1
    assert rep["per_skill"]["hotel-search"]["fn"] == 1
    assert rep["null_correct"] == 1            # 'hello' → fallback counts as correct null


def test_summarize_modes_weighted_delta():
    mono = [{"task_id": "t1", "domain": "ancillery", "score": 0.5},
            {"task_id": "t2", "domain": "ancillery", "score": 1.0}]
    orch = [{"task_id": "t1", "domain": "ancillery", "score": 1.0},
            {"task_id": "t2", "domain": "ancillery", "score": 1.0}]
    s = summarize_modes(mono, orch)
    assert s["per_domain"]["ancillery"]["delta"] == 0.25
    assert s["overall_delta"] > 0
