import json, pathlib, pytest

def load_output():
    p = pathlib.Path("task_output.json")
    if not p.exists():
        pytest.skip("No task_output.json found")
    return json.loads(p.read_text())

def test_score_above_threshold():
    output = load_output()
    score = output.get("score", 0.0)
    assert score >= 0.5, f"LLM judge score {{score}} below 0.5 threshold"

def test_has_response():
    output = load_output()
    assert output.get("response"), "No response in output"
