# tests/test_skill_manager.py
import pytest, pathlib
from eval.skill_manager import (
    validate_skill, list_skills, read_skill, write_skill, SkillInfo
)

VALID_SKILL = """# test-skill

## When to Use
When user asks about tests.

## Workflow
1. Do the thing
2. Return the result

## When NOT to Use
- Never in production
"""

INVALID_SKILL = """# test-skill

## When to Use
When user asks about tests.
"""

@pytest.fixture
def skill_dir(tmp_path):
    (tmp_path / "concrete" / "test-skill").mkdir(parents=True)
    (tmp_path / "concrete" / "test-skill" / "SKILL.md").write_text(VALID_SKILL)
    (tmp_path / "atomic").mkdir()
    (tmp_path / "abstract").mkdir()
    return tmp_path

def test_validate_valid():
    assert validate_skill(VALID_SKILL) == []

def test_validate_missing_workflow():
    errors = validate_skill(INVALID_SKILL)
    assert any("Workflow" in e for e in errors)

def test_list_skills(skill_dir):
    skills = list_skills(skills_dir=skill_dir)
    assert len(skills) == 1
    assert skills[0].name == "test-skill"
    assert skills[0].layer == "concrete"

def test_read_skill(skill_dir):
    content = read_skill("concrete", "test-skill", skills_dir=skill_dir)
    assert "## When to Use" in content

def test_write_skill(skill_dir):
    new_content = VALID_SKILL.replace("Do the thing", "Do the other thing")
    write_skill("concrete", "test-skill", new_content, skills_dir=skill_dir)
    assert "Do the other thing" in read_skill("concrete", "test-skill", skills_dir=skill_dir)

def test_write_skill_rejects_invalid(skill_dir):
    with pytest.raises(ValueError, match="Workflow"):
        write_skill("concrete", "test-skill", INVALID_SKILL, skills_dir=skill_dir)
