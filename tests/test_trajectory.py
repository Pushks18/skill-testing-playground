import pytest, uuid, pathlib
from eval.trajectory import (
    TrajectoryStep, TrajectoryRun, init_db, save_run, get_runs,
    classify_failure, FAILURE_MODES,
)

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "test_trajectory.db"
    monkeypatch.setattr("eval.trajectory.DB_PATH", db)
    init_db()
    return db

def make_run(tools_called=None, score=1.0, passed=True, failure_mode=None):
    run_id = str(uuid.uuid4())
    steps = []
    for i, t in enumerate(tools_called or []):
        steps.append(TrajectoryStep(
            run_id=run_id, task_id="t1", skill_name="test", condition="with_skill",
            step_num=i, node="tools", tool_name=t["name"],
            tool_params=t.get("params", {}), tool_result="ok",
            latency_ms=50, tokens=10,
        ))
    return TrajectoryRun(
        run_id=run_id, task_id="t1", skill_name="test", condition="with_skill",
        score=score, passed=passed, failure_mode=failure_mode, steps=steps,
        langsmith_url=None,
    )

def test_save_and_retrieve(tmp_db):
    run = make_run(tools_called=[{"name": "search_flights", "params": {"origin": "JFK"}}])
    save_run(run)
    runs = get_runs(task_id="t1")
    assert len(runs) == 1
    assert runs[0].run_id == run.run_id
    assert len(runs[0].steps) == 1
    assert runs[0].steps[0].tool_name == "search_flights"

def test_filter_failed_only(tmp_db):
    save_run(make_run(score=1.0, passed=True))
    save_run(make_run(score=0.0, passed=False, failure_mode="NO_TOOL_CALL"))
    all_runs = get_runs(task_id="t1")
    failed = get_runs(task_id="t1", failed_only=True)
    assert len(all_runs) == 2
    assert len(failed) == 1
    assert failed[0].failure_mode == "NO_TOOL_CALL"

def test_classify_no_tool_call():
    mode = classify_failure(
        tools_called=[], required_tools=["search_flights"], required_params={}
    )
    assert mode == "NO_TOOL_CALL"

def test_classify_wrong_tool():
    mode = classify_failure(
        tools_called=[{"name": "get_itinerary", "params": {}}],
        required_tools=["search_flights"], required_params={}
    )
    assert mode == "WRONG_TOOL"

def test_classify_missing_param():
    mode = classify_failure(
        tools_called=[{"name": "search_flights", "params": {"origin": "JFK"}}],
        required_tools=["search_flights"],
        required_params={"search_flights": ["origin", "destination", "date"]}
    )
    assert mode == "MISSING_PARAM"

def test_classify_multi_step_dropout():
    mode = classify_failure(
        tools_called=[{"name": "check_availability", "params": {"resource_id": "FL1", "date": "2026-07-01"}}],
        required_tools=["check_availability", "create_booking"],
        required_params={"check_availability": ["resource_id", "date"], "create_booking": ["flight_id", "passenger"]}
    )
    assert mode == "MULTI_STEP_DROPOUT"

def test_classify_partial_match():
    mode = classify_failure(
        tools_called=[{"name": "search_flights", "params": {"origin": "JFK", "destination": "LAX", "date": "2026-07-01"}}],
        required_tools=["search_flights", "search_hotels"],
        required_params={}
    )
    assert mode == "PARTIAL_MATCH"

def test_classify_no_failure_on_pass():
    mode = classify_failure(
        tools_called=[{"name": "search_flights", "params": {"origin": "JFK", "destination": "LAX", "date": "2026-07-01"}}],
        required_tools=["search_flights"],
        required_params={"search_flights": ["origin", "destination", "date"]}
    )
    assert mode is None
