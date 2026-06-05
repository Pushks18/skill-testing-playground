import json, pathlib, pytest

def load_output():
    p = pathlib.Path("task_output.json")
    if not p.exists():
        pytest.skip("No task_output.json found")
    return json.loads(p.read_text())

def test_has_response():
    output = load_output()
    assert output.get("response"), "No response generated"
