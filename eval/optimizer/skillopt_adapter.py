# eval/optimizer/skillopt_adapter.py
"""SkillOpt integration: two-target adapter for the travel eval.

TargetSpec describes WHAT is being optimized (a SKILL.md body, or one
optimizable key of agent/harness_config.yaml). TravelTaskLoader feeds the
domain's tasks through skillopt's deterministic ratio split. TravelEnvAdapter
plugs run_task into the ReflACT trainer's rollout/reflect stages.

Propose-only: nothing here writes to skills/ or agent/harness_config.yaml.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from dataclasses import dataclass
from typing import Literal, Optional

import yaml
from skillopt.datasets.base import BatchSpec, SplitDataLoader
from skillopt.envs.base import EnvAdapter
from skillopt.gradient.reflect import run_minibatch_reflect

from eval.run_task import run_task
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
            if not task_dir.is_dir():
                continue
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


class TravelEnvAdapter(EnvAdapter):
    """ReflACT adapter: rollout = run_task on the split's tasks, with the
    candidate artifact materialized per TargetSpec."""

    def __init__(
        self,
        spec: TargetSpec,
        mock_mcp_url: str = "http://localhost:8000",
        workers: int = 4,
        failure_only: bool = True,
        minibatch_size: int = 4,
        edit_budget: int = 3,
        **kwargs,
    ):
        self.spec = spec
        self.mock_mcp_url = mock_mcp_url
        self.workers = workers
        self.failure_only = failure_only
        self.minibatch_size = minibatch_size
        self.edit_budget = edit_budget
        self.dataloader = TravelTaskLoader(
            tasks_dir=spec.tasks_dir, domain=spec.domain, **kwargs)

    # ── trainer lifecycle (mirrors skillopt's SearchQA reference adapter) ──

    def setup(self, cfg: dict) -> None:
        super().setup(cfg)
        self.dataloader.setup(cfg)
        # The 0.1.0 wheel ships no prompt files; reflect/aggregate/clip crash
        # with FileNotFoundError without our replacements. Idempotent.
        from eval.optimizer.skillopt_prompts import install_prompts
        install_prompts()

    def get_dataloader(self):
        return self.dataloader

    def build_env_from_batch(self, batch: BatchSpec, **kwargs):
        return list(batch.payload or [])

    def build_train_env(self, batch_size: int, seed: int, **kwargs):
        batch = self.dataloader.build_train_batch(batch_size=batch_size, seed=seed, **kwargs)
        return self.build_env_from_batch(batch, **kwargs)

    def build_eval_env(self, env_num: int, split: str, seed: int, **kwargs):
        batch = self.dataloader.build_eval_batch(env_num=env_num, split=split, seed=seed, **kwargs)
        return self.build_env_from_batch(batch, **kwargs)

    # ── rollout: the real eval ─────────────────────────────────────────────

    def rollout(self, env_manager, skill_content: str, out_dir: str, **kwargs) -> list[dict]:
        items: list[dict] = env_manager
        out_path = pathlib.Path(out_dir)
        ctx = materialize_candidate(self.spec, skill_content, out_path)

        previous = os.environ.get("HARNESS_CONFIG_PATH")
        results: list[dict] = []
        try:
            if ctx.harness_config_path is not None:
                os.environ["HARNESS_CONFIG_PATH"] = str(ctx.harness_config_path)
            for item in items:
                r = run_task(item["task_path"], str(ctx.skill_path),
                             "with_skill", self.mock_mcp_url)
                results.append({
                    "id": item["id"],
                    "hard": int(r.passed_verifier),
                    "soft": float(r.score),
                    "fail_reason": r.judge_reasoning or "",
                    "task_type": self.spec.domain,
                    "question": item.get("question", ""),
                })
        finally:
            if previous is None:
                os.environ.pop("HARNESS_CONFIG_PATH", None)
            else:
                os.environ["HARNESS_CONFIG_PATH"] = previous

        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "rollout_results.json").write_text(json.dumps(results, indent=2))
        return results

    # ── reflect: delegate to skillopt's native machinery ───────────────────

    def reflect(self, results: list[dict], skill_content: str, out_dir: str, **kwargs):
        prediction_dir = kwargs.get("prediction_dir", os.path.join(out_dir, "predictions"))
        patches_dir = kwargs.get("patches_dir", os.path.join(out_dir, "patches"))
        return run_minibatch_reflect(
            results=results,
            skill_content=skill_content,
            prediction_dir=prediction_dir,
            patches_dir=patches_dir,
            workers=self.workers,
            failure_only=self.failure_only,
            minibatch_size=self.minibatch_size,
            edit_budget=self.edit_budget,
            random_seed=kwargs.get("random_seed"),
            error_system=self.get_error_minibatch_prompt(),
            success_system=self.get_success_minibatch_prompt(),
            step_buffer_context=kwargs.get("step_buffer_context", ""),
            meta_skill_context=kwargs.get("meta_skill_context", ""),
            update_mode=getattr(self, "_cfg", {}).get("skill_update_mode", "patch"),
        )

    def get_task_types(self) -> list[str]:
        return [self.spec.domain]
