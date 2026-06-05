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
