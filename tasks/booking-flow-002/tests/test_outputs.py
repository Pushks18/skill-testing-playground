import json, pathlib, pytest

def load_output():
    p = pathlib.Path("task_output.json")
    if not p.exists():
        pytest.skip("No task_output.json found")
    return json.loads(p.read_text())

def test_required_tools():
    output = load_output()
    tools_called = {t["name"] for t in output.get("tools_called", [])}
    required = ['create_booking']
    missing = [t for t in required if t not in tools_called]
    assert not missing, f"Missing tools: {missing}"

def test_required_params():
    output = load_output()
    tools_map = {t["name"]: t.get("params", {}) for t in output.get("tools_called", [])}
    required_params = {'create_booking': ['hotel_id', 'passenger']}
    for tool, params in required_params.items():
        if tool in tools_map:
            for p in params:
                assert p in tools_map[tool], f"Missing param {p} in {tool}"
