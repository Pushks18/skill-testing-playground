# tests/test_skill_task_coverage.py
"""Skills and tasks must stay on the same page.

Every task must belong to a real skill, and every evaluable skill must have
enough tasks to be A/B-tested. Fails loudly when someone adds a skill without
eval coverage or a task pointing at a skill that doesn't exist.
"""
from __future__ import annotations

import pathlib
import re
import collections

import pytest

TASKS_DIR = pathlib.Path("tasks")
SKILLS_ROOT = pathlib.Path("../travel-agent-skills/skills")

# Report-only detection skills: no action tools, not evaluable by tool_call
# verifiers (see docs/disruption-architecture-note.md in the skills repo).
# Remove an entry from this set once its report_judge tasks exist.
REPORT_ONLY_SKILLS = {
    "car-disruption-detection",
    "disruption-agent-common-policy",
    "experience-disruption-detection",
    "external-disruption-detection",
    "flight-delay-detection",
    "flight-disruption-detection",
    "flight-risk-detection",
    "gate-terminal-change",
    "stay-disruption-detection",
}

MIN_TASKS_PER_SKILL = 10


def _task_skill_counts() -> collections.Counter:
    counts: collections.Counter = collections.Counter()
    for toml in TASKS_DIR.glob("*/task.toml"):
        m = re.search(r'^skill\s*=\s*"([^"]+)"', toml.read_text(), re.M)
        counts[m.group(1) if m else f"(missing skill field: {toml.parent.name})"] += 1
    return counts


def _skills_on_disk() -> set[str]:
    found: set[str] = set()
    if not SKILLS_ROOT.exists():
        pytest.skip("travel-agent-skills repo not checked out next to the playground")
    for entry in SKILLS_ROOT.iterdir():
        if not entry.is_dir():
            continue
        if (entry / "SKILL.md").exists():
            found.add(entry.name)
        else:  # nested suite (e.g. disruption-skill/)
            found.update(
                sub.name for sub in entry.iterdir()
                if sub.is_dir() and (sub / "SKILL.md").exists()
            )
    return found


def test_every_task_points_at_a_real_skill():
    skills = _skills_on_disk()
    unknown = {s: n for s, n in _task_skill_counts().items() if s not in skills}
    assert not unknown, (
        f"tasks reference skills that don't exist in {SKILLS_ROOT}: {unknown} — "
        "fix the task.toml skill field or add the skill"
    )


def test_every_evaluable_skill_has_task_coverage():
    counts = _task_skill_counts()
    evaluable = _skills_on_disk() - REPORT_ONLY_SKILLS
    thin = {s: counts.get(s, 0) for s in evaluable if counts.get(s, 0) < MIN_TASKS_PER_SKILL}
    assert not thin, (
        f"evaluable skills below {MIN_TASKS_PER_SKILL} tasks: {thin} — "
        "register a taskgen domain and run scripts/expand_bank.py before this "
        "skill can be A/B-gated (or add it to REPORT_ONLY_SKILLS with a reason)"
    )


def test_report_only_list_matches_reality():
    # If someone gives a detection skill real tasks, force the allowlist update
    # so coverage expectations stay explicit.
    counts = _task_skill_counts()
    covered_anyway = {s for s in REPORT_ONLY_SKILLS if counts.get(s, 0) > 0}
    assert not covered_anyway, (
        f"skills in REPORT_ONLY_SKILLS now have tasks: {covered_anyway} — "
        "remove them from the allowlist"
    )
