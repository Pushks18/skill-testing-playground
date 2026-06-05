# tests/test_export_skill.py
"""TDD tests for eval.export_skill — Phase 4.2."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.export_skill import _discover_skills, main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SKILL_A_MD = """\
---
name: skill-alpha
description: Alpha skill for testing.
metadata:
  author: tester
  version: "1.2.3"
---

# Skill Alpha body
"""

SKILL_B_MD = """\
---
name: skill-beta
description: Beta skill for testing.
metadata:
  author: tester
  version: "0.5.0"
---

# Skill Beta body
"""

NESTED_SUB1_MD = """\
---
name: nested-sub1
description: Sub-skill one inside a nested suite.
metadata:
  author: suite-author
  version: "0.2.0"
---

# Sub1 body
"""

NESTED_SUB2_MD = """\
---
name: nested-sub2
description: Sub-skill two inside a nested suite.
metadata:
  author: suite-author
  version: "0.3.0"
---

# Sub2 body
"""


@pytest.fixture()
def skills_root(tmp_path: Path) -> Path:
    """Build a fake skills tree:
        skills/
          skill-alpha/SKILL.md        ← direct skill
          skill-beta/SKILL.md         ← direct skill
          nested-suite/               ← nested suite (no top-level SKILL.md)
            sub1/SKILL.md
            sub2/SKILL.md
          junk-dir/                   ← no SKILL.md anywhere → skip
            readme.txt
    """
    root = tmp_path / "skills"

    # Direct skills
    (root / "skill-alpha").mkdir(parents=True)
    (root / "skill-alpha" / "SKILL.md").write_text(SKILL_A_MD, encoding="utf-8")

    (root / "skill-beta").mkdir(parents=True)
    (root / "skill-beta" / "SKILL.md").write_text(SKILL_B_MD, encoding="utf-8")

    # Nested suite
    (root / "nested-suite" / "sub1").mkdir(parents=True)
    (root / "nested-suite" / "sub1" / "SKILL.md").write_text(NESTED_SUB1_MD, encoding="utf-8")
    (root / "nested-suite" / "sub2").mkdir(parents=True)
    (root / "nested-suite" / "sub2" / "SKILL.md").write_text(NESTED_SUB2_MD, encoding="utf-8")

    # Junk dir
    (root / "junk-dir").mkdir(parents=True)
    (root / "junk-dir" / "readme.txt").write_text("nothing here", encoding="utf-8")

    return root


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    return tmp_path / "output"


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------

def test_discover_finds_all_exportable_skills(skills_root: Path) -> None:
    found = _discover_skills(skills_root)
    names = [n for n, _ in found]
    assert "skill-alpha" in names
    assert "skill-beta" in names
    assert "sub1" in names
    assert "sub2" in names


def test_discover_skips_junk(skills_root: Path) -> None:
    found = _discover_skills(skills_root)
    names = [n for n, _ in found]
    assert "junk-dir" not in names
    assert "nested-suite" not in names  # suite itself should not appear


def test_discover_total_count(skills_root: Path) -> None:
    found = _discover_skills(skills_root)
    # skill-alpha, skill-beta, sub1, sub2
    assert len(found) == 4


# ---------------------------------------------------------------------------
# Export-all tests
# ---------------------------------------------------------------------------

def test_export_all_creates_correct_count(skills_root: Path, target: Path) -> None:
    rc = main(["--skills-root", str(skills_root), "--all", "--target", str(target)])
    assert rc == 0
    exported = [d for d in target.iterdir() if d.is_dir()]
    assert len(exported) == 4


def test_export_all_skill_dir_contents(skills_root: Path, target: Path) -> None:
    main(["--skills-root", str(skills_root), "--all", "--target", str(target)])
    alpha_dir = target / "skill-alpha"
    assert (alpha_dir / "SKILL.md").exists()
    assert (alpha_dir / "metadata.json").exists()


def test_export_all_skill_md_content_is_verbatim(skills_root: Path, target: Path) -> None:
    main(["--skills-root", str(skills_root), "--all", "--target", str(target)])
    exported_md = (target / "skill-alpha" / "SKILL.md").read_text(encoding="utf-8")
    assert exported_md == SKILL_A_MD


# ---------------------------------------------------------------------------
# metadata.json content
# ---------------------------------------------------------------------------

def test_metadata_json_fields(skills_root: Path, target: Path) -> None:
    main(["--skills-root", str(skills_root), "--all", "--target", str(target)])
    meta = json.loads((target / "skill-alpha" / "metadata.json").read_text())
    assert meta["name"] == "skill-alpha"
    assert meta["description"] == "Alpha skill for testing."
    assert meta["version"] == "1.2.3"
    assert meta["author"] == "tester"
    assert meta["source"] == "travel-agent-skills"
    assert "exported_at" in meta


def test_metadata_exported_at_is_iso(skills_root: Path, target: Path) -> None:
    from datetime import datetime
    main(["--skills-root", str(skills_root), "--all", "--target", str(target)])
    meta = json.loads((target / "skill-beta" / "metadata.json").read_text())
    # Should parse without error
    dt = datetime.fromisoformat(meta["exported_at"])
    assert dt.tzinfo is not None  # timezone-aware


# ---------------------------------------------------------------------------
# Nested suite flattening
# ---------------------------------------------------------------------------

def test_nested_suite_sub_skills_exported_flat(skills_root: Path, target: Path) -> None:
    main(["--skills-root", str(skills_root), "--all", "--target", str(target)])
    assert (target / "sub1" / "SKILL.md").exists()
    assert (target / "sub2" / "SKILL.md").exists()


def test_nested_suite_metadata(skills_root: Path, target: Path) -> None:
    main(["--skills-root", str(skills_root), "--all", "--target", str(target)])
    meta = json.loads((target / "sub1" / "metadata.json").read_text())
    assert meta["name"] == "nested-sub1"
    assert meta["author"] == "suite-author"
    assert meta["version"] == "0.2.0"


# ---------------------------------------------------------------------------
# Single skill export
# ---------------------------------------------------------------------------

def test_export_single_skill(skills_root: Path, target: Path) -> None:
    rc = main([
        "--skills-root", str(skills_root),
        "--skill", "skill-beta",
        "--target", str(target),
    ])
    assert rc == 0
    assert (target / "skill-beta" / "SKILL.md").exists()
    assert not (target / "skill-alpha").exists()


def test_export_unknown_skill_returns_error(skills_root: Path, target: Path) -> None:
    rc = main([
        "--skills-root", str(skills_root),
        "--skill", "does-not-exist",
        "--target", str(target),
    ])
    assert rc != 0


# ---------------------------------------------------------------------------
# No-overwrite without --force
# ---------------------------------------------------------------------------

def test_no_overwrite_without_force(skills_root: Path, target: Path) -> None:
    # First export
    main(["--skills-root", str(skills_root), "--all", "--target", str(target)])
    # Write a sentinel value into the exported SKILL.md
    sentinel = "SENTINEL CONTENT"
    (target / "skill-alpha" / "SKILL.md").write_text(sentinel, encoding="utf-8")
    # Second export without --force should skip
    main(["--skills-root", str(skills_root), "--all", "--target", str(target)])
    # Sentinel must still be there
    content = (target / "skill-alpha" / "SKILL.md").read_text()
    assert content == sentinel


def test_force_overwrites(skills_root: Path, target: Path) -> None:
    # First export
    main(["--skills-root", str(skills_root), "--all", "--target", str(target)])
    # Write sentinel
    sentinel = "SENTINEL CONTENT"
    (target / "skill-alpha" / "SKILL.md").write_text(sentinel, encoding="utf-8")
    # Second export WITH --force should overwrite
    main(["--skills-root", str(skills_root), "--all", "--target", str(target), "--force"])
    content = (target / "skill-alpha" / "SKILL.md").read_text()
    assert content != sentinel
    assert content == SKILL_A_MD


# ---------------------------------------------------------------------------
# --list writes nothing
# ---------------------------------------------------------------------------

def test_list_writes_nothing(skills_root: Path, target: Path, capsys: pytest.CaptureFixture) -> None:
    rc = main(["--skills-root", str(skills_root), "--list"])
    assert rc == 0
    # Target must not have been created
    assert not target.exists()
    captured = capsys.readouterr()
    assert "skill-alpha" in captured.out
    assert "skill-beta" in captured.out
    assert "sub1" in captured.out


# ---------------------------------------------------------------------------
# Safety: refuse target inside skills-root
# ---------------------------------------------------------------------------

def test_refuse_target_inside_skills_root(skills_root: Path) -> None:
    nested_target = skills_root / "exports"
    rc = main([
        "--skills-root", str(skills_root),
        "--all",
        "--target", str(nested_target),
    ])
    assert rc != 0
    # Make sure nothing was written
    assert not nested_target.exists()


# ---------------------------------------------------------------------------
# --target required for export
# ---------------------------------------------------------------------------

def test_target_required_without_list(skills_root: Path) -> None:
    rc = main(["--skills-root", str(skills_root), "--all"])
    assert rc != 0
