# eval/skill_loader.py
"""Parse agentskills.io SKILL.md format: strip YAML frontmatter, return structured skill."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

_FRONTMATTER = re.compile(r'^---\n(.*?)\n---\n(.*)', re.DOTALL)


@dataclass
class LoadedSkill:
    name: str
    description: str
    body: str
    version: str
    author: str
    raw_path: Path


def load_skill(path: Path) -> Optional[LoadedSkill]:
    """Parse an agentskills.io SKILL.md: strip YAML frontmatter, return structured skill.

    Falls back gracefully when frontmatter is absent (plain markdown skills).
    """
    skill_file = path / "SKILL.md" if path.is_dir() else path
    if not skill_file.exists():
        return None

    content = skill_file.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(content)
    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            frontmatter = {}
        body = match.group(2).strip()
    else:
        frontmatter = {}
        body = content.strip()

    skill_dir = skill_file.parent
    return LoadedSkill(
        name=frontmatter.get("name", skill_dir.name),
        description=frontmatter.get("description", ""),
        body=body,
        version=frontmatter.get("metadata", {}).get("version", "0.1.0"),
        author=frontmatter.get("metadata", {}).get("author", ""),
        raw_path=skill_file,
    )
