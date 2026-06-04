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


@dataclass
class TrajectoryFeatures:
    """Deterministic features extracted from one eval run, compared against its A/B counterpart (typically the with_skill side vs no_skill)."""
    task_id: str
    domain: str
    task_weight: float
    skill_injected: bool
    # Tool behavior
    n_tools_called: int
    called_any_tool: bool
    first_tool_name: Optional[str]
    expected_first_tool: Optional[str]
    first_tool_correct: bool
    n_wrong_tool_calls: int
    n_repeated_tool_calls: int
    # Param quality
    n_calls_missing_required_params: int
    param_match_rate: float
    # Control flow
    n_steps: int
    step_delta_vs_no_skill: int
    ended_without_tool_on_tool_task: bool
    looped_without_completion: bool
    # Output / outcome
    output_is_verbal_only: bool
    verifier_score: float
    delta_vs_no_skill: float


@dataclass
class FailureClassification:
    """Layer attribution for one failed task — routes the optimizer to the right artifact."""
    task_id: str
    layer: Literal[
        "harness:base_prompt", "harness:tool_description", "harness:node_prompt",
        "skill:content", "skill:over_prescription", "skill:trigger",
    ]
    confidence: float
    target_artifact: str
    evidence: Dict


@dataclass
class LayerCluster:
    """Failures grouped by (layer, domain). One cluster routes to one artifact.

    Distinct from eval.optimizer.propose_skill.FailureCluster, which clusters
    by domain to propose *new* skills.
    """
    layer: str
    domain: str
    task_ids: List
    dominant_failure_mode: str
    target_artifact: str
    n_failures: int = field(init=False)

    def __post_init__(self) -> None:
        self.n_failures = len(self.task_ids)
