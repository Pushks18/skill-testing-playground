# eval/optimizer/skillopt_adapter.py
"""SkillOpt integration: two-target adapter for the travel eval.

TargetSpec describes WHAT is being optimized (a SKILL.md body, or one
optimizable key of agent/harness_config.yaml). TravelTaskLoader feeds the
domain's tasks through skillopt's deterministic ratio split. TravelEnvAdapter
plugs run_task into the ReflACT trainer's rollout/reflect stages.

Propose-only: nothing here writes to skills/ or agent/harness_config.yaml.
"""
from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass
from typing import Literal, Optional

import yaml

from eval.skill_loader import load_skill


@dataclass
class TargetSpec:
    """What the optimizer is editing, and the context to evaluate candidates."""
    kind: Literal["skill", "harness"]
    key: str                      # harness: config key; skill: skill name
    skill_path: pathlib.Path      # skill injected during rollout (source skill for kind=skill)
    domain: str
    tasks_dir: pathlib.Path
    harness_config_path: pathlib.Path


@dataclass
class CandidateContext:
    """Where a materialized candidate lives for one rollout."""
    skill_path: pathlib.Path                       # skill dir to inject
    harness_config_path: Optional[pathlib.Path]    # set only for harness targets


def initial_artifact(spec: TargetSpec) -> str:
    """The current text of the artifact under optimization."""
    if spec.kind == "skill":
        skill = load_skill(spec.skill_path)
        if skill is None:
            raise FileNotFoundError(f"no SKILL.md under {spec.skill_path}")
        return skill.body
    config = yaml.safe_load(spec.harness_config_path.read_text())
    value = config[spec.key]
    if isinstance(value, dict):
        return yaml.safe_dump(value, sort_keys=False)
    return str(value)


def _skill_frontmatter(skill_path: pathlib.Path) -> str:
    """Raw frontmatter block (--- ... ---) of the source SKILL.md."""
    content = (skill_path / "SKILL.md").read_text()
    m = re.match(r"^(---\n.*?\n---\n)", content, re.DOTALL)
    return m.group(1) if m else ""


def materialize_candidate(
    spec: TargetSpec,
    artifact_text: str,
    out_dir: pathlib.Path,
) -> CandidateContext:
    """Write a candidate artifact to disk, ready for rollout.

    skill target  → temp skill dir with original frontmatter + candidate body
    harness target → full config copy with the one key substituted
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if spec.kind == "skill":
        candidate_dir = out_dir / "candidate_skill"
        candidate_dir.mkdir(exist_ok=True)
        frontmatter = _skill_frontmatter(spec.skill_path)
        sep = "\n" if frontmatter else ""
        (candidate_dir / "SKILL.md").write_text(f"{frontmatter}{sep}{artifact_text.strip()}\n")
        return CandidateContext(skill_path=candidate_dir, harness_config_path=None)

    # harness target
    config = yaml.safe_load(spec.harness_config_path.read_text())
    current = config[spec.key]
    if isinstance(current, dict):
        try:
            new_value = yaml.safe_load(artifact_text)
        except yaml.YAMLError as e:
            raise ValueError(f"candidate artifact is not valid YAML for key "
                             f"{spec.key!r}: {e}") from e
        if not isinstance(new_value, dict):
            raise ValueError(f"candidate artifact is not valid YAML mapping for key {spec.key!r}")
        config[spec.key] = new_value
    else:
        config[spec.key] = artifact_text
    candidate_path = out_dir / "candidate_harness_config.yaml"
    candidate_path.write_text(yaml.safe_dump(config, sort_keys=False))
    return CandidateContext(skill_path=spec.skill_path, harness_config_path=candidate_path)


from skillopt.datasets.base import BatchSpec, SplitDataLoader


class TravelTaskLoader(SplitDataLoader):
    """Feeds one domain's tasks/ dirs through skillopt's ratio split (train:val:test)."""

    def __init__(self, tasks_dir: pathlib.Path, domain: str, **kwargs):
        kwargs.setdefault("split_mode", "ratio")
        kwargs.setdefault("split_ratio", "5:3:2")
        super().__init__(data_path=str(tasks_dir), **kwargs)
        self.tasks_dir = pathlib.Path(tasks_dir)
        self.domain = domain

    def load_raw_items(self, data_path: str) -> list[dict]:
        items: list[dict] = []
        for task_dir in sorted(pathlib.Path(data_path).iterdir()):
            toml_path = task_dir / "task.toml"
            instr_path = task_dir / "instruction.md"
            if not (toml_path.exists() and instr_path.exists()):
                continue
            m = re.search(r'^domain\s*=\s*"([^"]+)"', toml_path.read_text(), re.MULTILINE)
            if not m or m.group(1) != self.domain:
                continue
            items.append({
                "id": task_dir.name,
                "question": instr_path.read_text().strip()[:300],
                "task_type": self.domain,
                "task_path": str(task_dir),
            })
        return items
