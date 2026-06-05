# eval/optimizer/optimize.py
"""Two-target optimization driver (Slice 3): cluster → SkillOpt trainer → proposal.

Reads failure_classification.json (Slice 1), resolves each qualifying cluster
to a target artifact (SKILL.md body or one harness-config key), runs the
ReflACT trainer with the mixed gate, and writes *_proposed.* files plus an
optimization_report.json under eval/optimizer_output/.

PROPOSE-ONLY. Never writes to skills/ or agent/harness_config.yaml, never
commits, never opens PRs. A human reviews every proposal.

Usage:
    python -m eval.optimizer.optimize --classification failure_classification.json
    python -m eval.optimizer.optimize --cluster 0 --dry-run
"""
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import argparse
import datetime
import json
import os
import pathlib
import sys

import httpx
import yaml

from eval.optimizer.skillopt_adapter import (
    TargetSpec, TravelEnvAdapter, initial_artifact, _skill_frontmatter,
)

DEFAULT_TASKS_DIR = pathlib.Path("tasks")
DEFAULT_HARNESS_CONFIG = pathlib.Path("agent/harness_config.yaml")
DEFAULT_SKILLS_ROOT = pathlib.Path("../travel-agent-skills/skills")
OUTPUT_ROOT = pathlib.Path("eval/optimizer_output")


# ── cluster → target resolution ─────────────────────────────────────────────

def resolve_target(cluster: dict, optimizable: list[str] | None = None) -> tuple[str, str]:
    """('harness'|'skill', key). Harness keys checked against the whitelist."""
    target = cluster["target_artifact"]
    if "::" in target:                      # agent/harness_config.yaml::<key>
        key = target.split("::", 1)[1]
        if optimizable is not None:
            roots = {entry.split(".")[0] for entry in optimizable}
            if key.split(".")[0] not in roots:
                raise ValueError(f"harness key {key!r} is not optimizable "
                                 f"(whitelist: {optimizable})")
        return "harness", key
    # skills/<name>/SKILL.md
    parts = pathlib.PurePosixPath(target).parts
    return "skill", parts[parts.index("skills") + 1]


def qualifying_clusters(clusters: list[dict]) -> list[dict]:
    """Harness clusters qualify at n>=1; skill clusters need n>=2 (too thin below)."""
    out = []
    for c in clusters:
        n = c.get("n_failures", len(c.get("task_ids", [])))
        if c["layer"].startswith("harness:") and n >= 1:
            out.append(c)
        elif c["layer"].startswith("skill:") and n >= 2:
            out.append(c)
    return out


def estimate_rollout_calls(n_train: int, n_selection: int, n_test: int, epochs: int) -> int:
    """baseline(selection) + per-epoch (train rollout + selection eval)
    + eval_test runs the test split twice (baseline + best). Findings §8.2-8.3."""
    return n_selection + epochs * (n_train + n_selection) + 2 * n_test


# ── proposal output ──────────────────────────────────────────────────────────

def write_proposed(
    *,
    kind: str,
    key: str,
    artifact_text: str,
    out_dir: pathlib.Path,
    harness_config_path: pathlib.Path | None,
    skill_path: pathlib.Path | None,
) -> pathlib.Path:
    """Write the proposed artifact file. Sources are never modified."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if kind == "harness":
        config = yaml.safe_load(harness_config_path.read_text())
        current = config[key]
        config[key] = yaml.safe_load(artifact_text) if isinstance(current, dict) else artifact_text
        out_path = out_dir / "harness_config_proposed.yaml"
        out_path.write_text(yaml.safe_dump(config, sort_keys=False))
        return out_path
    frontmatter = _skill_frontmatter(skill_path)
    sep = "\n" if frontmatter else ""
    out_path = out_dir / "SKILL_proposed.md"
    out_path.write_text(f"{frontmatter}{sep}{artifact_text.strip()}\n")
    return out_path


# ── preflight ────────────────────────────────────────────────────────────────

def preflight(mock_mcp_url: str) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("preflight: OPENAI_API_KEY is not set")
    try:
        httpx.get(mock_mcp_url, timeout=3)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        sys.exit(f"preflight: mock MCP server not reachable at {mock_mcp_url} — "
                 "start it: .venv/bin/python eval/mock_mcp/server.py &")


# ── per-cluster run ──────────────────────────────────────────────────────────

def run_cluster(cluster: dict, args) -> dict:
    harness_config_path = pathlib.Path(args.harness_config)
    optimizable = yaml.safe_load(harness_config_path.read_text()).get("optimizable", [])
    kind, key = resolve_target(
        cluster,
        optimizable=optimizable if "::" in cluster["target_artifact"] else None,
    )

    skill_name = (key if kind == "skill"
                  else _skill_for_domain(cluster["domain"]))
    skill_path = pathlib.Path(args.skills_root) / skill_name

    spec = TargetSpec(kind=kind, key=key, skill_path=skill_path,
                      domain=cluster["domain"], tasks_dir=pathlib.Path(args.tasks_dir),
                      harness_config_path=harness_config_path)

    run_tag = f"{cluster['domain']}_{kind}_{key.replace('.', '-')}_{datetime.date.today().isoformat()}"
    out_root = OUTPUT_ROOT / run_tag

    adapter = TravelEnvAdapter(spec=spec, mock_mcp_url=args.mock_mcp_url,
                               split_seed=args.seed, seed=args.seed,
                               must_split_ids=cluster.get("task_ids", []))
    baseline_text = initial_artifact(spec)

    n_items = len(adapter.dataloader.load_raw_items(str(spec.tasks_dir)))
    n_train, n_sel, n_test = _split_counts(n_items)

    # Load config early so num_epochs is available for the estimate.
    from skillopt.config import load_config, flatten_config
    cfg = flatten_config(load_config(args.config))

    est_calls = estimate_rollout_calls(n_train, n_sel, n_test, cfg.get("num_epochs", 5))
    print(f"[{run_tag}] target={kind}:{key} tasks={n_items} (split {n_train}/{n_sel}/{n_test}) "
          f"~{est_calls} rollout calls (gpt-4o-mini)")

    if args.dry_run:
        return {"run": run_tag, "dry_run": True, "estimated_rollout_calls": est_calls}

    # File writes happen only on real runs (after the dry-run guard).
    cfg["out_root"] = str(out_root)
    cfg["seed"] = args.seed
    out_root.mkdir(parents=True, exist_ok=True)
    # skill_init MUST be a file path — a text literal is silently treated as a
    # nonexistent path and the skill starts blank (spike findings §1)
    skill_init_path = out_root / "initial_artifact.md"
    skill_init_path.write_text(baseline_text)
    cfg["skill_init"] = str(skill_init_path)

    from skillopt.engine.trainer import ReflACTTrainer
    try:
        train_result = ReflACTTrainer(cfg, adapter).train()
    except Exception as e:
        crash_report = {
            "run": run_tag, "target": f"{kind}:{key}", "cluster": cluster,
            "crashed": True, "error": f"{type(e).__name__}: {e}",
            "estimated_rollout_calls": est_calls,
        }
        (out_root / "optimization_report.json").write_text(json.dumps(crash_report, indent=2))
        print(f"[{run_tag}] CRASHED: {e} — partial spend recorded in {out_root}/optimization_report.json")
        raise

    # Best artifact: out_root/best_skill.md, overwritten at each accept (findings §3)
    best_skill_file = out_root / "best_skill.md"
    best_text = best_skill_file.read_text() if best_skill_file.exists() else baseline_text

    # Held-out test: the trainer runs it itself when eval_test=true (findings §4),
    # scoring BOTH skill_init (baseline) and best_skill on the test split.
    w = cfg.get("gate_mixed_weight", 0.5)
    base_score = _mixed_from(train_result.get("baseline_test_hard"),
                             train_result.get("baseline_test_soft"), w)
    best_score = _mixed_from(train_result.get("test_hard"),
                             train_result.get("test_soft"), w)

    sel_baseline = train_result.get("baseline_selection_hard")
    sel_best = train_result.get("best_selection_hard")
    selection_improved = (sel_baseline is not None and sel_best is not None
                          and sel_best > sel_baseline)
    test_regressed = best_score < base_score
    report = {
        "run": run_tag, "target": f"{kind}:{key}", "cluster": cluster,
        "baseline_test_mixed": base_score, "best_test_mixed": best_score,
        "baseline_selection_score": sel_baseline,
        "best_selection_score": sel_best,
        "selection_improved": selection_improved,
        "test_regressed": test_regressed,
        "improved": selection_improved and not test_regressed,
        "evidence_note": ("improvement evidence comes from the selection split "
                          "(contains failure tasks); the held-out test split guards "
                          "non-regression on remaining tasks"),
        "estimated_rollout_calls": est_calls,
        "train_result": _jsonable(train_result),
        "review_checklist": [
            "Read the proposed diff against the current artifact",
            "Run ab_compare on a SECOND skill before merging a harness change",
            "Verify the test-split tasks were never used for edit selection",
        ],
    }
    if report["improved"]:
        proposed = write_proposed(kind=kind, key=key, artifact_text=best_text,
                                  out_dir=out_root, harness_config_path=harness_config_path,
                                  skill_path=skill_path)
        report["proposed_file"] = str(proposed)
        print(f"[{run_tag}] IMPROVED on selection split ({sel_baseline} → {sel_best}), test did not regress — proposal: {proposed}")
    else:
        print(f"[{run_tag}] no proposal: selection_improved={selection_improved}, test_regressed={test_regressed} (selection {sel_baseline} → {sel_best}, test {base_score:.2f} → {best_score:.2f})")

    (out_root / "optimization_report.json").write_text(json.dumps(report, indent=2))
    return report


def _mixed_from(hard, soft, w: float = 0.5) -> float:
    """Mixed gate score from the trainer's returned hard/soft test scores."""
    if hard is None or soft is None:
        return 0.0
    return (1 - w) * float(hard) + w * float(soft)


def _split_counts(n: int, ratio=(5, 3, 2)) -> tuple[int, int, int]:
    total = sum(ratio)
    train = round(n * ratio[0] / total)
    sel = round(n * ratio[1] / total)
    return train, sel, n - train - sel


def _skill_for_domain(domain: str) -> str:
    """Map a task domain to its skill dir (mirrors propose_skill mapping)."""
    from eval.optimizer.propose_skill import _DOMAIN_TO_SKILL_NAME
    return _DOMAIN_TO_SKILL_NAME.get(domain, domain.replace("_", "-"))


def _jsonable(obj):
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Two-target skill/harness optimizer (propose-only).")
    parser.add_argument("--classification", default="failure_classification.json")
    parser.add_argument("--cluster", type=int, default=None, help="index into clusters; default all qualifying")
    parser.add_argument("--config", default="eval/optimizer/skillopt_config.yaml")
    parser.add_argument("--tasks-dir", default=str(DEFAULT_TASKS_DIR))
    parser.add_argument("--harness-config", default=str(DEFAULT_HARNESS_CONFIG))
    parser.add_argument("--skills-root", default=str(DEFAULT_SKILLS_ROOT))
    parser.add_argument("--mock-mcp-url", default="http://localhost:8000")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = json.loads(pathlib.Path(args.classification).read_text())
    clusters = data.get("clusters", [])
    targets = ([clusters[args.cluster]] if args.cluster is not None
               else qualifying_clusters(clusters))
    if not targets:
        print("No qualifying clusters.")
        return

    if not args.dry_run:
        preflight(args.mock_mcp_url)

    for cluster in targets:
        run_cluster(cluster, args)


if __name__ == "__main__":
    main()
