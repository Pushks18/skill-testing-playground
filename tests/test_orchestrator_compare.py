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


def test_agent_router_singleton_constructed_once_under_concurrency(monkeypatch):
    """50 threads racing _get_agent_router must construct AgentRouter exactly
    once. The unlocked singleton loaded the embedding model up to 21x in the
    2026-06-06 comparison run — a memory spike that got the process SIGKILLed."""
    import threading
    import eval.run_task as rt

    monkeypatch.setattr(rt, "_AGENT_ROUTER", None)
    constructed = []
    barrier = threading.Barrier(20)

    class _FakeRouter:
        def __init__(self, *a, **kw):
            constructed.append(1)
            # The real constructor loads a sentence-transformer (seconds);
            # a wide window makes the unlocked race deterministic.
            import time
            time.sleep(0.05)

    import agent.router
    monkeypatch.setattr(agent.router, "AgentRouter", _FakeRouter)

    results = []

    def hit():
        barrier.wait()
        results.append(rt._get_agent_router("http://localhost:8000"))

    threads = [threading.Thread(target=hit) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(constructed) == 1, f"AgentRouter constructed {len(constructed)}x"
    assert all(r is results[0] for r in results)


def test_run_task_wrapper_retries_transient_connection_error(monkeypatch):
    """One transient APIConnectionError must not kill a 25-minute bank run."""
    import httpx
    import openai
    import eval.orchestrator_compare as oc

    calls = []

    def flaky_run_task(**kw):
        calls.append(1)
        if len(calls) == 1:
            raise openai.APIConnectionError(request=httpx.Request("POST", "http://x"))
        return "ok"

    import eval.run_task as rt
    monkeypatch.setattr(rt, "run_task", flaky_run_task)
    result = oc._run_task_wrapper("tasks/x", None, "orchestrated",
                                  "http://localhost:8000", "orchestrated")
    assert result == "ok"
    assert len(calls) == 2
