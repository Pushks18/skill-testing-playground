# tests/test_specialists.py
import pathlib
import pytest

from agent.specialists import SKILL_TOOLS, build_specialist_agent, specialist_config

SKILLS_ROOT = pathlib.Path("../travel-agent-skills/skills")


def test_skill_tools_reference_real_tools():
    from eval.taskgen import VALID_TOOLS
    for skill, tools in SKILL_TOOLS.items():
        assert set(tools) <= set(VALID_TOOLS), skill


def test_specialist_config_scoped():
    cfg = specialist_config("ancillery-skill", SKILLS_ROOT)
    assert cfg["tools_subset"] == SKILL_TOOLS["ancillery-skill"]
    assert "Ancillery" in cfg["skill_content"] or "ancillary" in cfg["skill_content"].lower()


def test_specialist_config_unlisted_skill_gets_all_tools():
    cfg = specialist_config("planning-skill", SKILLS_ROOT)
    assert cfg["tools_subset"] is None          # None = all 10


def test_specialist_config_missing_skill_raises():
    with pytest.raises(FileNotFoundError):
        specialist_config("no-such-skill", SKILLS_ROOT)


def test_build_specialist_agent_compiles(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    agent = build_specialist_agent("fare-rules", SKILLS_ROOT, mock_mcp_url="http://localhost:8000")
    assert agent is not None
