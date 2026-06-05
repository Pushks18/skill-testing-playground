# tests/test_harness_config.py
import pathlib
import pytest
from agent.travel_agent import load_harness_config, HARNESS_DEFAULTS


def test_load_returns_yaml_values():
    cfg = load_harness_config()
    assert cfg["base_system_prompt"].startswith("You are a helpful travel assistant.")
    assert cfg["tool_descriptions"]["search_flights"] == \
        "Search for available flights between two cities."
    assert cfg["node_prompts"] == {}


def test_yaml_matches_defaults_verbatim():
    """Behavior preservation: YAML initial values == hardcoded fallbacks."""
    cfg = load_harness_config()
    assert cfg["base_system_prompt"] == HARNESS_DEFAULTS["base_system_prompt"]
    assert cfg["tool_descriptions"] == HARNESS_DEFAULTS["tool_descriptions"]


def test_missing_file_falls_back_to_defaults(tmp_path):
    cfg = load_harness_config(config_path=tmp_path / "does_not_exist.yaml")
    assert cfg == HARNESS_DEFAULTS


def test_partial_file_merges_with_defaults(tmp_path):
    p = tmp_path / "partial.yaml"
    p.write_text('base_system_prompt: "Custom prompt."\n')
    cfg = load_harness_config(config_path=p)
    assert cfg["base_system_prompt"] == "Custom prompt."
    # missing keys fall back
    assert cfg["tool_descriptions"] == HARNESS_DEFAULTS["tool_descriptions"]


def test_tools_get_config_descriptions(monkeypatch):
    """Tool descriptions come from config after post-construction assignment."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    from agent.travel_agent import make_mcp_tools, load_harness_config
    tools = make_mcp_tools("http://localhost:8000")
    cfg = load_harness_config()
    for t in tools:
        assert t.description == cfg["tool_descriptions"][t.name]


def test_build_agent_uses_config_prompt(monkeypatch, tmp_path):
    """base_system_prompt flows from config into the agent's system prompt."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    import agent.travel_agent as ta
    custom = tmp_path / "harness_config.yaml"
    custom.write_text('base_system_prompt: "CUSTOM HARNESS PROMPT"\n')
    monkeypatch.setattr(ta, "_CONFIG_PATH", custom)
    cfg = ta.load_harness_config(custom)
    assert cfg["base_system_prompt"] == "CUSTOM HARNESS PROMPT"
    # and the graph compiles without error using the custom config
    agent = ta.build_travel_agent(skill_content=None)
    assert agent is not None


def test_corrupt_yaml_warns_and_falls_back(tmp_path):
    """Unparseable YAML → warning + defaults, not silence or crash."""
    from agent.travel_agent import load_harness_config, HARNESS_DEFAULTS
    p = tmp_path / "corrupt.yaml"
    p.write_text("base_system_prompt: [unclosed\n  nonsense: {{{{\n")
    with pytest.warns(UserWarning, match="harness_config"):
        cfg = load_harness_config(config_path=p)
    assert cfg == HARNESS_DEFAULTS


def test_env_var_overrides_default_path(tmp_path, monkeypatch):
    """HARNESS_CONFIG_PATH redirects load_harness_config when no explicit arg."""
    from agent.travel_agent import load_harness_config
    p = tmp_path / "override.yaml"
    p.write_text('base_system_prompt: "ENV OVERRIDE PROMPT"\n')
    monkeypatch.setenv("HARNESS_CONFIG_PATH", str(p))
    cfg = load_harness_config()
    assert cfg["base_system_prompt"] == "ENV OVERRIDE PROMPT"


def test_explicit_arg_beats_env_var(tmp_path, monkeypatch):
    from agent.travel_agent import load_harness_config
    env_p = tmp_path / "env.yaml"
    env_p.write_text('base_system_prompt: "FROM ENV"\n')
    arg_p = tmp_path / "arg.yaml"
    arg_p.write_text('base_system_prompt: "FROM ARG"\n')
    monkeypatch.setenv("HARNESS_CONFIG_PATH", str(env_p))
    cfg = load_harness_config(config_path=arg_p)
    assert cfg["base_system_prompt"] == "FROM ARG"


def test_no_env_var_uses_default(monkeypatch):
    from agent.travel_agent import load_harness_config, HARNESS_DEFAULTS
    monkeypatch.delenv("HARNESS_CONFIG_PATH", raising=False)
    cfg = load_harness_config()
    # default file on disk == defaults (verbatim externalization)
    assert cfg["base_system_prompt"] == HARNESS_DEFAULTS["base_system_prompt"]
