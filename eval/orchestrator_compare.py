# eval/orchestrator_compare.py
"""Mono-vs-orchestrated comparison harness.

Two questions answered here:
1. Router accuracy (free, no agent calls): route labeled requests + task
   instructions and report precision/recall per skill.
2. End-to-end quality (paid): run mono vs orchestrated for selected domains,
   report weighted score deltas and misroutes.

Usage
─────
    # Router accuracy only (free — no agent calls, no API key needed)
    python -m eval.orchestrator_compare --accuracy-only

    # Pilot (cheap): ancillery + disruption, 3 trials each mode
    python -m eval.orchestrator_compare --domains ancillery,disruption --trials 3

    # Full bank comparison
    python -m eval.orchestrator_compare --trials 3 --output results/orchestrator_compare.json
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import argparse
import asyncio
import json
import os
import pathlib
import re
import sys
import time

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from eval.gate_check import TASK_WEIGHTS

# ---------------------------------------------------------------------------
# Label alias map: legacy labels → canonical skill dir names
# ---------------------------------------------------------------------------

# From propose_skill._DOMAIN_TO_SKILL_NAME (domain→skill) + explicit legacy aliases
_LABEL_ALIAS: dict[str, str] = {
    # Legacy label names used in labeled_requests.json that differ from skill dirs
    "book-itinerary": "booking-skill",
    # _DOMAIN_TO_SKILL_NAME entries that use underscores or different names
    "flight_search": "flight-search",
    "hotel_search": "hotel-search",
    "booking_flow": "booking-skill",
    "fare_rules": "fare-rules",
    "edge_cases": "modify-booking",
    "itinerary_build": "planning-skill",
    "ancillery": "ancillery-skill",
    "disruption": "disruption-handling",
    "baggage": "baggage-policy",
    "loyalty": "loyalty-rewards",
    "visa": "visa-requirements",
    "insurance": "travel-insurance",
}


def _normalize_label(raw_label) -> str | None:
    """Map a raw label from labeled_requests.json to a canonical skill dir name.

    Returns None for null / "none" / "null" labels (out-of-scope requests).
    """
    if raw_label is None:
        return None
    s = str(raw_label).strip().lower()
    if s in ("none", "null", ""):
        return None
    # Apply alias map; fall through to the raw value (already canonical)
    return _LABEL_ALIAS.get(raw_label, raw_label)


# ---------------------------------------------------------------------------
# Pure functions (testable without network)
# ---------------------------------------------------------------------------

def router_accuracy(
    labels: list[tuple[str, str | None]],
    routed: list[str],
    fallback: str = "planning-skill",
) -> dict:
    """Compute per-skill TP/FP/FN and null-routing stats.

    Parameters
    ----------
    labels:
        List of (text, expected_skill_or_None). expected_skill is the canonical
        skill dir name; None means the request is out-of-scope (no skill expected).
    routed:
        Parallel list of router outputs (skill names).
    fallback:
        The skill name returned by the router when confidence is below threshold.

    Returns
    -------
    dict with:
        per_skill: {skill_name: {tp, fp, fn, precision, recall}}
        null_correct: int  (None-labeled items routed to fallback — correct)
        null_wrong:   int  (None-labeled items NOT routed to fallback)
        overall: {precision, recall}
    """
    assert len(labels) == len(routed), "labels and routed must be the same length"

    per_skill: dict[str, dict] = {}

    def _get(skill):
        if skill not in per_skill:
            per_skill[skill] = {"tp": 0, "fp": 0, "fn": 0}
        return per_skill[skill]

    null_correct = 0
    null_wrong = 0

    for (text, expected), prediction in zip(labels, routed):
        if expected is None:
            # Out-of-scope request: correct iff router falls back
            if prediction == fallback:
                null_correct += 1
            else:
                null_wrong += 1
                _get(prediction)["fp"] += 1
        else:
            if prediction == expected:
                _get(expected)["tp"] += 1
            else:
                # Predicted the wrong skill
                _get(prediction)["fp"] += 1
                _get(expected)["fn"] += 1

    # Compute precision / recall per skill
    for skill, counts in per_skill.items():
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        counts["precision"] = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        counts["recall"] = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    # Overall micro precision / recall (across all in-scope items)
    total_tp = sum(c["tp"] for c in per_skill.values())
    total_fp = sum(c["fp"] for c in per_skill.values())
    total_fn = sum(c["fn"] for c in per_skill.values())
    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0

    return {
        "per_skill": per_skill,
        "null_correct": null_correct,
        "null_wrong": null_wrong,
        "overall": {
            "precision": overall_precision,
            "recall": overall_recall,
            "total_labeled": len(labels),
            "in_scope": sum(1 for _, e in labels if e is not None),
            "out_of_scope": sum(1 for _, e in labels if e is None),
        },
    }


def summarize_modes(
    mono_results: list[dict],
    orch_results: list[dict],
) -> dict:
    """Compute per-domain score deltas (orchestrated - mono) using TASK_WEIGHTS.

    Parameters
    ----------
    mono_results / orch_results:
        List of dicts, each with at least: task_id, domain, score.
        Parallel by task_id.

    Returns
    -------
    dict with:
        per_domain: {domain: {mono_mean, orch_mean, delta, weight}}
        overall_delta: float  (weighted mean of per-domain deltas)
        misroutes: list of dicts from orch_results where misroute=True
    """
    # Index by task_id
    mono_by_id = {r["task_id"]: r for r in mono_results}
    orch_by_id = {r["task_id"]: r for r in orch_results}

    # Group scores by domain
    domain_mono: dict[str, list[float]] = {}
    domain_orch: dict[str, list[float]] = {}

    for task_id, mono_r in mono_by_id.items():
        domain = mono_r["domain"]
        domain_mono.setdefault(domain, []).append(mono_r["score"])
        if task_id in orch_by_id:
            domain_orch.setdefault(domain, []).append(orch_by_id[task_id]["score"])

    per_domain: dict[str, dict] = {}
    for domain in domain_mono:
        mono_scores = domain_mono[domain]
        orch_scores = domain_orch.get(domain, [])
        mono_mean = sum(mono_scores) / len(mono_scores) if mono_scores else 0.0
        orch_mean = sum(orch_scores) / len(orch_scores) if orch_scores else 0.0
        delta = orch_mean - mono_mean
        weight = TASK_WEIGHTS.get(domain, 1.0)
        per_domain[domain] = {
            "mono_mean": mono_mean,
            "orch_mean": orch_mean,
            "delta": delta,
            "weight": weight,
            "n_tasks": len(mono_scores),
        }

    # Weighted overall delta
    total_weight = sum(v["weight"] for v in per_domain.values())
    overall_delta = (
        sum(v["delta"] * v["weight"] for v in per_domain.values()) / total_weight
        if total_weight > 0 else 0.0
    )

    # Collect misroutes from orch_results
    misroutes = [r for r in orch_results if r.get("misroute")]

    return {
        "per_domain": per_domain,
        "overall_delta": overall_delta,
        "misroutes": misroutes,
        "total_weight": total_weight,
    }


# ---------------------------------------------------------------------------
# Route report (free: embeddings only, no agent calls)
# ---------------------------------------------------------------------------

def route_report(
    skills_root: pathlib.Path = pathlib.Path("../travel-agent-skills/skills"),
    labeled_path: str = "trigger/labeled_requests.json",
    tasks_dir: str = "tasks",
    fallback: str = "planning-skill",
) -> dict:
    """Route all labeled requests + all task instructions; return accuracy tables.

    No agent calls — uses AgentRouter.route_skill (embeddings only).
    """
    from agent.router import AgentRouter

    router = AgentRouter(skills_root)

    # --- Load labeled requests ---
    req_labels: list[tuple[str, str | None]] = []
    req_routed: list[str] = []

    labeled_data = json.loads(pathlib.Path(labeled_path).read_text())
    for item in labeled_data:
        text = item["request"]
        raw_label = item.get("expected_skill")
        expected = _normalize_label(raw_label)
        routed_skill = router.route_skill(text)
        req_labels.append((text, expected))
        req_routed.append(routed_skill)

    req_accuracy = router_accuracy(req_labels, req_routed, fallback=fallback)

    # --- Load task instructions ---
    task_labels: list[tuple[str, str | None]] = []
    task_routed: list[str] = []

    tasks_path = pathlib.Path(tasks_dir)
    if tasks_path.exists():
        for task_dir in sorted(tasks_path.iterdir()):
            toml_path = task_dir / "task.toml"
            instr_path = task_dir / "instruction.md"
            if not toml_path.exists() or not instr_path.exists():
                continue
            content = toml_path.read_text()
            m = re.search(r'^skill\s*=\s*"([^"]+)"', content, re.MULTILINE)
            skill_label = m.group(1) if m else None
            text = instr_path.read_text().strip()
            routed_skill = router.route_skill(text)
            task_labels.append((text, skill_label))
            task_routed.append(routed_skill)

    task_accuracy = router_accuracy(task_labels, task_routed, fallback=fallback) if task_labels else {}

    return {
        "requests": req_accuracy,
        "tasks": task_accuracy,
    }


# ---------------------------------------------------------------------------
# Async eval bank (paid: run agent calls)
# ---------------------------------------------------------------------------

EVAL_CONCURRENCY = int(os.environ.get("EVAL_CONCURRENCY", "50"))


async def _run_guarded(sem: asyncio.Semaphore, loop, *args, **kwargs):
    async with sem:
        return await loop.run_in_executor(None, lambda: _run_task_wrapper(*args, **kwargs))


def _run_task_wrapper(task_path, skill_path, condition, mock_mcp_url, agent_mode,
                      _max_attempts: int = 2):
    """One bounded retry on transient connection errors — a single dropped
    connection must not kill a 25-minute bank run (it did on 2026-06-06)."""
    import openai

    import eval.run_task as _rt

    last_exc = None
    for attempt in range(_max_attempts):
        try:
            return _rt.run_task(
                task_path=str(task_path),
                skill_path=skill_path,
                condition=condition,
                mock_mcp_url=mock_mcp_url,
                agent_mode=agent_mode,
            )
        except (openai.APIConnectionError, openai.APITimeoutError) as e:
            last_exc = e
            print(f"  [retry {attempt + 1}/{_max_attempts}] {task_path}: {e}", flush=True)
            time.sleep(2 * (attempt + 1))
    raise last_exc


def _load_tasks_for_domains(
    tasks_dir: pathlib.Path,
    domains: list[str] | None,
) -> list[tuple[pathlib.Path, str, str]]:
    """Return list of (task_dir, skill_name, domain) for matching tasks."""
    results = []
    for task_dir in sorted(tasks_dir.iterdir()):
        toml_path = task_dir / "task.toml"
        if not toml_path.exists():
            continue
        content = toml_path.read_text()
        m_domain = re.search(r'^domain\s*=\s*"([^"]+)"', content, re.MULTILINE)
        m_skill = re.search(r'^skill\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if not m_domain or not m_skill:
            continue
        domain = m_domain.group(1)
        skill = m_skill.group(1)
        if domains is None or domain in domains:
            results.append((task_dir, skill, domain))
    return results


async def run_bank(
    domains: list[str] | None,
    trials: int,
    mode: str,
    mock_mcp_url: str,
    skills_root: pathlib.Path = pathlib.Path("../travel-agent-skills/skills"),
    tasks_dir: pathlib.Path = pathlib.Path("tasks"),
) -> list[dict]:
    """Run all tasks for the selected domains in a single mode, best-of-N.

    mode: "mono" or "orchestrated"

    Returns list of per-task row dicts:
        task_id, domain, score (best), routed_skill (orchestrated only),
        designated_skill, misroute (bool)
    """
    tasks = _load_tasks_for_domains(tasks_dir, domains)
    if not tasks:
        print(f"  No tasks found for domains={domains}", flush=True)
        return []

    sem = asyncio.Semaphore(EVAL_CONCURRENCY)
    loop = asyncio.get_event_loop()

    total = len(tasks) * trials
    print(f"  [{mode}] {len(tasks)} tasks × {trials} trials = {total} calls", flush=True)

    async def _task_best_of_n(task_dir, designated_skill, domain):
        if mode == "mono":
            skill_path = str(skills_root / designated_skill)
            condition = "with_skill"
        else:  # orchestrated
            skill_path = None
            condition = "orchestrated"

        futures = [
            _run_guarded(sem, loop, task_dir, skill_path, condition, mock_mcp_url, mode)
            for _ in range(trials)
        ]
        results = await asyncio.gather(*futures)

        best = max(results, key=lambda r: r.score)
        routed = best.skill_name if mode == "orchestrated" else None
        misroute = (routed is not None) and (routed != designated_skill)

        return {
            "task_id": best.task_id,
            "domain": domain,
            "score": best.score,
            "routed_skill": routed,
            "designated_skill": designated_skill,
            "misroute": misroute,
        }

    rows = await asyncio.gather(*[
        _task_best_of_n(td, sk, dom) for td, sk, dom in tasks
    ])
    return list(rows)


# ---------------------------------------------------------------------------
# Preflight check
# ---------------------------------------------------------------------------

def _preflight(mock_mcp_url: str, check_key: bool = True) -> bool:
    """Check that mock MCP is reachable and OPENAI_API_KEY is set."""
    import urllib.request
    import urllib.error
    ok = True
    if check_key and not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set.", flush=True)
        ok = False

    def _reachable(url: str) -> bool:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except urllib.error.HTTPError:
            # Got an HTTP response (e.g. 404) — server is up, just no route there
            return True
        except Exception:
            return False

    if not _reachable(mock_mcp_url + "/health") and not _reachable(mock_mcp_url):
        print(f"ERROR: Mock MCP not reachable at {mock_mcp_url}.", flush=True)
        ok = False
    return ok


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def _print_accuracy(label: str, rep: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Router Accuracy — {label}")
    print(f"{'=' * 60}")
    overall = rep.get("overall", {})
    print(f"  Overall  P={overall.get('precision', 0):.2f}  R={overall.get('recall', 0):.2f}"
          f"   ({overall.get('in_scope', 0)} in-scope, {overall.get('out_of_scope', 0)} out-of-scope)")
    print(f"  Null-routing: {rep.get('null_correct', 0)} correct, {rep.get('null_wrong', 0)} wrong")
    print(f"  {'Skill':<30} {'TP':>4} {'FP':>4} {'FN':>4} {'P':>6} {'R':>6}")
    print(f"  {'-'*54}")
    for skill, c in sorted(rep.get("per_skill", {}).items()):
        print(f"  {skill:<30} {c['tp']:>4} {c['fp']:>4} {c['fn']:>4} {c['precision']:>6.2f} {c['recall']:>6.2f}")


def _print_comparison(summary: dict) -> None:
    print(f"\n{'=' * 60}")
    print("  Mono vs Orchestrated — Quality Delta")
    print(f"{'=' * 60}")
    print(f"  Overall weighted delta: {summary['overall_delta']:+.3f}")
    print(f"\n  {'Domain':<25} {'Mono':>6} {'Orch':>6} {'Delta':>7} {'Weight':>7}")
    print(f"  {'-'*52}")
    for domain, v in sorted(summary["per_domain"].items()):
        print(f"  {domain:<25} {v['mono_mean']:>6.2f} {v['orch_mean']:>6.2f}"
              f" {v['delta']:>+7.3f} {v['weight']:>7.1f}")
    misroutes = summary.get("misroutes", [])
    if misroutes:
        print(f"\n  Misroutes ({len(misroutes)}):")
        for r in misroutes:
            print(f"    {r['task_id']}: routed={r['routed_skill']} expected={r['designated_skill']}")
    else:
        print("\n  No misroutes detected.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Mono-vs-orchestrated comparison and router accuracy report."
    )
    parser.add_argument("--accuracy-only", action="store_true",
                        help="Only compute router accuracy (free, no agent calls).")
    parser.add_argument("--domains", default=None,
                        help="Comma-separated domain names to evaluate (default: all).")
    parser.add_argument("--trials", type=int, default=3,
                        help="Number of trials per task per mode (best-of-N).")
    parser.add_argument("--output", default=None,
                        help="JSON output path (default: results/orchestrator_compare.json).")
    parser.add_argument("--mock-mcp-url", default=os.environ.get("MOCK_MCP_URL", "http://localhost:8000"))
    args = parser.parse_args()

    skills_root = pathlib.Path("../travel-agent-skills/skills")
    domains = [d.strip() for d in args.domains.split(",")] if args.domains else None

    if args.accuracy_only:
        rep = route_report(skills_root=skills_root)
        _print_accuracy("Labeled Requests (60)", rep["requests"])
        if rep["tasks"]:
            _print_accuracy("Task Instructions", rep["tasks"])
        sys.exit(0)

    # Paid path — preflight
    if not _preflight(args.mock_mcp_url, check_key=True):
        sys.exit(1)

    mock_url = args.mock_mcp_url

    print(f"\nRunning mono bank…")
    mono_rows = asyncio.run(run_bank(
        domains=domains,
        trials=args.trials,
        mode="mono",
        mock_mcp_url=mock_url,
        skills_root=skills_root,
    ))

    print(f"\nRunning orchestrated bank…")
    orch_rows = asyncio.run(run_bank(
        domains=domains,
        trials=args.trials,
        mode="orchestrated",
        mock_mcp_url=mock_url,
        skills_root=skills_root,
    ))

    summary = summarize_modes(mono_rows, orch_rows)
    _print_comparison(summary)

    output = args.output or "results/orchestrator_compare.json"
    pathlib.Path(output).parent.mkdir(exist_ok=True)
    pathlib.Path(output).write_text(json.dumps({
        "mono": mono_rows,
        "orchestrated": orch_rows,
        "summary": summary,
    }, indent=2))
    print(f"\nResults written to {output}")
