# eval/skill_router.py
"""Semantic skill router — matches a task instruction to the best skill using embeddings.

Uses sentence-transformers (all-MiniLM-L6-v2, ~80 MB, runs locally, no API key needed).
The model is loaded once and reused across calls.

Usage
─────
    from eval.skill_router import SkillRouter
    from pathlib import Path

    router = SkillRouter.from_skill_dir(Path("../travel-agent-skills/skills"))
    match = router.route("Find me a hotel in Paris for next weekend")
    print(match.skill_name, match.score)   # hotel-search  0.87
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class RouteMatch:
    skill_name: str
    score: float          # cosine similarity 0.0–1.0
    description: str


class SkillRouter:
    """Embed skill descriptions once; score incoming instructions at query time."""

    _model = None   # shared across all instances

    def __init__(self, skills: dict[str, str]):
        """
        skills: {skill_name: description_text}
        """
        self._skills = skills
        self._embeddings: dict[str, list[float]] = {}
        self._embed_skills()

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_skill_dir(cls, skills_dir: Path) -> "SkillRouter":
        """Load all SKILL.md files from a directory and build the router."""
        skills: dict[str, str] = {}
        for skill_dir in sorted(skills_dir.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            description = _extract_description(skill_file)
            if description:
                skills[skill_dir.name] = description
        if not skills:
            raise ValueError(f"No skills found in {skills_dir}")
        return cls(skills)

    @classmethod
    def from_skill_paths(cls, paths: list[Path]) -> "SkillRouter":
        """Build router from a list of individual skill directories."""
        skills: dict[str, str] = {}
        for skill_dir in paths:
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            description = _extract_description(skill_file)
            if description:
                skills[skill_dir.name] = description
        return cls(skills)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(self, instruction: str, threshold: float = 0.30) -> Optional[RouteMatch]:
        """Return the best-matching skill for an instruction, or None if below threshold."""
        model = self._get_model()
        import numpy as np

        query_emb = model.encode(instruction, normalize_embeddings=True)
        best_name, best_score = None, -1.0

        for name, emb in self._embeddings.items():
            score = float(np.dot(query_emb, emb))
            if score > best_score:
                best_score = score
                best_name = name

        if best_name is None or best_score < threshold:
            return None
        return RouteMatch(
            skill_name=best_name,
            score=best_score,
            description=self._skills[best_name],
        )

    def rank(self, instruction: str) -> list[RouteMatch]:
        """Return all skills ranked by similarity to instruction (highest first)."""
        model = self._get_model()
        import numpy as np

        query_emb = model.encode(instruction, normalize_embeddings=True)
        matches = []
        for name, emb in self._embeddings.items():
            score = float(np.dot(query_emb, emb))
            matches.append(RouteMatch(skill_name=name, score=score, description=self._skills[name]))
        return sorted(matches, key=lambda m: m.score, reverse=True)

    # ------------------------------------------------------------------
    # Task bank helper
    # ------------------------------------------------------------------

    def tasks_for_skill(self, skill_name: str, tasks_dir: Path, threshold: float = 0.30) -> list[Path]:
        """
        Return task dirs that match skill_name.
        First tries exact match on task.toml `skill` field.
        Falls back to semantic similarity on task instruction when no exact match exists.
        """
        import re as _re

        exact, unmatched = [], []
        for task_dir in sorted(tasks_dir.iterdir()):
            toml_path = task_dir / "task.toml"
            if not toml_path.exists():
                continue
            content = toml_path.read_text()
            m = _re.search(r'^skill\s*=\s*"([^"]+)"', content, _re.MULTILINE)
            if m:
                if m.group(1) == skill_name:
                    exact.append(task_dir)
            else:
                unmatched.append(task_dir)

        if exact:
            return exact

        # Fallback: semantic match on instruction text
        semantic = []
        for task_dir in unmatched:
            instr_path = task_dir / "instruction.md"
            if not instr_path.exists():
                continue
            instruction = instr_path.read_text().strip()
            match = self.route(instruction, threshold=threshold)
            if match and match.skill_name == skill_name:
                semantic.append(task_dir)
        return semantic

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _embed_skills(self) -> None:
        model = self._get_model()
        for name, description in self._skills.items():
            self._embeddings[name] = model.encode(description, normalize_embeddings=True)

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            from sentence_transformers import SentenceTransformer
            cls._model = SentenceTransformer("all-MiniLM-L6-v2")
        return cls._model


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_FRONTMATTER = re.compile(r'^---\n(.*?)\n---\n', re.DOTALL)


def _extract_description(skill_file: Path) -> str:
    content = skill_file.read_text(encoding="utf-8")
    m = _FRONTMATTER.match(content)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
            return fm.get("description", "")
        except yaml.YAMLError:
            pass
    # Fall back to first non-empty line
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            return line
    return ""
