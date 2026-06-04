# eval/skill_manager.py
"""Read, write, validate SKILL.md files and shell out to git + eval."""
from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path("skills")
LAYERS = ["atomic", "concrete", "abstract"]
REQUIRED_SECTIONS = ["# ", "## When to Use", "## Workflow"]


@dataclass
class SkillInfo:
    name: str
    layer: str
    path: Path
    content: str
    last_commit: str
    last_modified: str
    last_eval_score: Optional[float] = None
    last_regression_rate: Optional[float] = None


def validate_skill(content: str) -> list:
    errors = []
    for section in REQUIRED_SECTIONS:
        if section not in content:
            errors.append(f"Missing required section: '{section}'")
    if len(content.strip()) < 50:
        errors.append("Skill content too short (< 50 chars)")
    return errors


def list_skills(skills_dir: Path = None) -> list:
    root = skills_dir or SKILLS_DIR
    result = []
    for layer in LAYERS:
        layer_dir = root / layer
        if not layer_dir.exists():
            continue
        for skill_dir in sorted(layer_dir.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            commit, date = _git_log(skill_file)
            result.append(SkillInfo(
                name=skill_dir.name,
                layer=layer,
                path=skill_file,
                content=skill_file.read_text(),
                last_commit=commit,
                last_modified=date,
            ))
    return result


def read_skill(layer: str, name: str, skills_dir: Path = None) -> str:
    root = skills_dir or SKILLS_DIR
    return (root / layer / name / "SKILL.md").read_text()


def write_skill(layer: str, name: str, content: str, skills_dir: Path = None):
    errors = validate_skill(content)
    if errors:
        raise ValueError("; ".join(errors))
    root = skills_dir or SKILLS_DIR
    path = root / layer / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def commit_skill(layer: str, name: str, message: str = None) -> str:
    path = SKILLS_DIR / layer / name / "SKILL.md"
    msg = message or f"feat: update skill {name}"
    subprocess.run(["git", "add", str(path)], check=True)
    result = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
    if result.returncode != 0:
        return result.stderr.strip()
    return result.stdout.strip().split("\n")[0]


def get_skill_history(layer: str, name: str) -> list:
    path = SKILLS_DIR / layer / name / "SKILL.md"
    result = subprocess.run(
        ["git", "log", "--oneline", "-10", "--", str(path)],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        return []
    return [{"hash": line[:7], "message": line[8:]}
            for line in result.stdout.strip().split("\n") if line]


def run_eval(layer: str, name: str, trials: int = 3) -> str:
    result = subprocess.run(
        [".venv/bin/python3.11", "-m", "eval.ab_compare",
         "--skill", f"{layer}/{name}", "--trials", str(trials)],
        capture_output=True, text=True, cwd="."
    )
    return result.stdout + result.stderr


def load_last_eval_results(name: str) -> Optional[dict]:
    path = Path("results") / f"{name}_ab_results.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if not data:
        return None
    total_w = sum(r.get("task_weight", 1.0) for r in data)
    weighted_delta = sum(r["delta"] * r.get("task_weight", 1.0) for r in data) / total_w
    regression_rate = sum(1 for r in data if r["delta"] < 0) / len(data)
    return {"weighted_delta": round(weighted_delta, 3), "regression_rate": round(regression_rate, 2)}


def _git_log(path: Path):
    result = subprocess.run(
        ["git", "log", "--format=%h|%ad", "--date=short", "-1", "--", str(path)],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        parts = result.stdout.strip().split("|")
        return parts[0], parts[1] if len(parts) > 1 else ""
    return "—", "—"
