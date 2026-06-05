import json, pathlib, pytest

def load_output():
    p = pathlib.Path("task_output.json")
    if not p.exists():
        pytest.skip("No task_output.json found")
    return json.loads(p.read_text())

def test_required_tools():
    output = load_output()
    tools_called = {t["name"] for t in output.get("tools_called", [])}
    required = ['add_ancillary']
    missing = [t for t in required if t not in tools_called]
    assert not missing, f"Missing tools: {missing}"
