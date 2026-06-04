from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional, List, Dict


@dataclass
class EvalResult:
    task_id: str
    domain: str
    skill_name: Optional[str]
    skill_version: Optional[str]
    score: float
    steps: int
    tools_called: List
    tool_params: Dict
    langsmith_run_id: str
    passed_verifier: bool
    judge_reasoning: Optional[str]
    latency_ms: int
    tokens_used: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class ABResult:
    skill_name: str
    task_id: str
    domain: str
    task_weight: float
    no_skill: EvalResult
    with_skill: EvalResult
    delta: float
    delta_significant: bool
    regression: bool
    step_delta: int
    token_delta: int
    latency_delta_ms: int = 0
    cost_delta_usd: float = 0.0

    @classmethod
    def from_pair(
        cls,
        skill_name: str,
        no_skill: EvalResult,
        with_skill: EvalResult,
        task_weight: float,
    ) -> ABResult:
        delta = with_skill.score - no_skill.score
        return cls(
            skill_name=skill_name,
            task_id=no_skill.task_id,
            domain=no_skill.domain,
            task_weight=task_weight,
            no_skill=no_skill,
            with_skill=with_skill,
            delta=delta,
            delta_significant=abs(delta) > 0.05,
            regression=delta < 0,
            step_delta=with_skill.steps - no_skill.steps,
            token_delta=with_skill.tokens_used - no_skill.tokens_used,
            latency_delta_ms=with_skill.latency_ms - no_skill.latency_ms,
            cost_delta_usd=with_skill.cost_usd - no_skill.cost_usd,
        )


@dataclass
class GateDecision:
    verdict: Literal["PASS", "WARN", "SOFT_BLOCK", "BLOCK"]
    tier: int
    weighted_delta: float
    regression_rate: float
    flagged_tasks: List
    langsmith_experiment_url: str
    override_allowed: bool


@dataclass
class SkillCoverageMetrics:
    skill_name: str
    trigger_precision: float
    trigger_recall: float
    no_trigger_precision: float
    coverage_precision: float
    coverage_recall: float
    optimizer_strategy: str


@dataclass
class SkillMeta:
    name: str
    layer: int
    path: str
    depends_on: List
    abstracted_by: List
    eval_score: Optional[float]
    coverage_metrics: Optional[SkillCoverageMetrics]
    last_eval: Optional[str]
    version: str
