# tests/test_taskgen.py
import pathlib
import pytest

from eval.taskgen import validate_draft, VALID_TOOLS, DOMAIN_SKILL, DOMAIN_TARGETS

GOOD_TOML = '''[task]
id = "disruption-101"
domain = "disruption"
skill = "disruption-handling"
verifier = "tool_call_check"
weight = 2.0

[expected]
tools = ["search_flights", "modify_booking"]
'''


def _draft(tmp_path, task_id="disruption-101", toml=GOOD_TOML, instruction="My flight was cancelled, rebook me."):
    d = tmp_path / task_id
    d.mkdir(parents=True)
    if toml is not None:
        (d / "task.toml").write_text(toml)
    if instruction is not None:
        (d / "instruction.md").write_text(instruction)
    return d


def test_validate_good_draft(tmp_path):
    errors = validate_draft(_draft(tmp_path))
    assert errors == []


def test_validate_rejects_unknown_tool(tmp_path):
    bad = GOOD_TOML.replace('"modify_booking"', '"teleport_passenger"')
    errors = validate_draft(_draft(tmp_path, toml=bad))
    assert any("teleport_passenger" in e for e in errors)


def test_validate_rejects_id_dir_mismatch(tmp_path):
    d = _draft(tmp_path, task_id="disruption-999")   # toml says disruption-101
    errors = validate_draft(d)
    assert any("id" in e.lower() for e in errors)


def test_validate_rejects_missing_instruction(tmp_path):
    d = _draft(tmp_path, instruction=None)
    errors = validate_draft(d)
    assert any("instruction" in e.lower() for e in errors)


def test_validate_rejects_bad_verifier(tmp_path):
    bad = GOOD_TOML.replace("tool_call_check", "vibes_check")
    errors = validate_draft(_draft(tmp_path, toml=bad))
    assert any("verifier" in e.lower() for e in errors)


def test_domain_constants_consistent():
    assert set(DOMAIN_TARGETS) <= set(DOMAIN_SKILL)
    assert len(VALID_TOOLS) == 10
