# eval/taskgen.py
"""Task bank expansion pipeline: generate → validate → dedupe → calibrate → promote.

LLM-drafted tasks land in tasks_drafts/<domain>/ and pass four gates before
entering tasks/: structural validation, embedding near-duplicate rejection,
single-trial no_skill calibration, and HUMAN review of REVIEW.md. The promote
subcommand is the only path into tasks/ and requires the human-edited sheet.

Usage:
    python -m eval.taskgen generate --domain disruption --count 12
    python -m eval.taskgen validate --domain disruption
    python -m eval.taskgen dedupe --domain disruption
    python -m eval.taskgen calibrate --domain disruption
    python -m eval.taskgen promote --domain disruption
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import argparse
import json
import os
import pathlib
import re
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from eval.run_task import run_task

TASKS_DIR = pathlib.Path("tasks")
DRAFTS_DIR = pathlib.Path("tasks_drafts")

VALID_TOOLS = frozenset({
    "search_flights", "search_hotels", "check_availability", "get_fare_rules",
    "validate_passenger", "create_booking", "modify_booking", "cancel_booking",
    "get_itinerary", "add_ancillary",
})
VALID_VERIFIERS = frozenset({"tool_call_check", "llm_judge"})

DOMAIN_SKILL = {
    "ancillery": "ancillery-skill",
    "booking_flow": "booking-skill",
    "fare_rules": "fare-rules",
    "itinerary_build": "planning-skill",
    "trip_planning": "planning-skill",
    "flight_search": "flight-search",
    "edge_cases": "modify-booking",
    "hotel_search": "hotel-search",
    "disruption": "disruption-handling",   # skill does not exist yet — intentional
}

# domain → (count to generate, default weight, id prefix)
DOMAIN_TARGETS = {
    "ancillery":      (10, 1.5, "ancillery"),
    "booking_flow":   (12, 3.0, "booking-flow"),
    "fare_rules":     (10, 1.0, "fare-rules"),
    "itinerary_build": (10, 1.5, "itinerary"),
    "disruption":     (12, 2.0, "disruption"),
    "edge_cases":     (6, 0.5, "edge-mixed"),
    "flight_search":  (4, 2.0, "flight-search"),
    "trip_planning":  (4, 1.5, "planning"),
}


def _read_toml(path: pathlib.Path) -> dict:
    """Parse a task.toml, tolerating the legacy colon-style inline tables."""
    raw = path.read_text()
    raw = re.sub(r"\{[^}]+\}", lambda m: m.group(0).replace(": ", " = ").replace(":", " = "), raw)
    return tomllib.loads(raw)


def validate_draft(draft_dir: pathlib.Path) -> list[str]:
    """Gate 1: structural validation. Returns [] when clean."""
    errors: list[str] = []
    toml_path = draft_dir / "task.toml"
    instr_path = draft_dir / "instruction.md"

    if not toml_path.exists():
        return [f"{draft_dir.name}: missing task.toml"]
    if not instr_path.exists() or not instr_path.read_text().strip():
        errors.append(f"{draft_dir.name}: missing or empty instruction.md")

    try:
        meta = _read_toml(toml_path)
    except Exception as e:  # noqa: BLE001 — any parse failure is a validation error
        return errors + [f"{draft_dir.name}: task.toml parse error: {e}"]

    task = meta.get("task", {})
    expected = meta.get("expected", {})

    if task.get("id") != draft_dir.name:
        errors.append(f"{draft_dir.name}: task id {task.get('id')!r} does not match directory name")
    for field in ("id", "domain", "skill", "verifier", "weight"):
        if field not in task:
            errors.append(f"{draft_dir.name}: missing [task] field {field!r}")
    if task.get("verifier") not in VALID_VERIFIERS:
        errors.append(f"{draft_dir.name}: invalid verifier {task.get('verifier')!r}")
    if task.get("domain") in DOMAIN_SKILL and task.get("skill") != DOMAIN_SKILL[task["domain"]]:
        errors.append(f"{draft_dir.name}: skill {task.get('skill')!r} does not match domain mapping")

    unknown = [t for t in expected.get("tools", []) if t not in VALID_TOOLS]
    if unknown:
        errors.append(f"{draft_dir.name}: unknown tools {unknown}")
    if task.get("verifier") == "tool_call_check" and not expected.get("tools"):
        errors.append(f"{draft_dir.name}: tool_call_check requires expected.tools")
    return errors


def _embed(texts: list[str]) -> list[list[float]]:
    """MiniLM embeddings (lazy import — model load is slow)."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(texts, normalize_embeddings=True).tolist()


def _cos(a: list[float], b: list[float]) -> float:
    """Cosine similarity (defensive norms; MiniLM vectors are already normalized)."""
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(y * y for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def find_near_duplicates(
    drafts: dict[str, str],
    existing: dict[str, str],
    threshold: float = 0.90,
) -> list[tuple[str, str, float]]:
    """Gate 2: (draft_id, matched_id, similarity) for every draft too close to
    an existing instruction or an earlier draft in the same batch.
    Strictly-greater comparison: a pair at exactly `threshold` is NOT flagged."""
    draft_ids = list(drafts)
    all_texts = [drafts[d] for d in draft_ids] + list(existing.values())
    vecs = _embed(all_texts)
    draft_vecs = vecs[: len(draft_ids)]
    existing_vecs = list(zip(existing.keys(), vecs[len(draft_ids):]))

    dups: list[tuple[str, str, float]] = []
    kept: list[tuple[str, list[float]]] = []
    for did, dvec in zip(draft_ids, draft_vecs):
        hit = None
        for eid, evec in existing_vecs:
            sim = _cos(dvec, evec)
            if sim > threshold:
                hit = (did, eid, round(sim, 3)); break
        if hit is None:
            for kid, kvec in kept:
                sim = _cos(dvec, kvec)
                if sim > threshold:
                    hit = (did, kid, round(sim, 3)); break
        if hit:
            dups.append(hit)
        else:
            kept.append((did, dvec))
    return dups


def calibrate_drafts(draft_dirs: list[pathlib.Path], mock_mcp_url: str) -> dict:
    """Gate 3: single no_skill trial per draft. Classes: baseline-pass /
    baseline-fail / broken. Single-trial is a coarse triage, not a metric."""
    report: dict = {}
    for d in draft_dirs:
        try:
            r = run_task(str(d), None, "no_skill", mock_mcp_url)
            cls = "baseline-pass" if r.passed_verifier else "baseline-fail"
            report[d.name] = {"class": cls, "score": float(r.score),
                              "detail": (r.judge_reasoning or "")[:120]}
        except Exception as e:  # noqa: BLE001 — broken drafts must not kill the batch
            report[d.name] = {"class": "broken", "score": 0.0,
                              "detail": f"{type(e).__name__}: {e}"[:120]}
    return report


def write_review_sheet(
    domain_dir: pathlib.Path,
    draft_dirs: list[pathlib.Path],
    calibration: dict,
    dups: list[tuple[str, str, float]],
) -> pathlib.Path:
    """Gate 4 input: human-editable REVIEW.md. Reviewer changes KEEP→DROP per row."""
    dup_ids = {d for d, _, _ in dups}
    lines = [
        f"# Review sheet — {domain_dir.name}",
        "",
        "Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as",
        "needed, then run: `python -m eval.taskgen promote --domain " + domain_dir.name + "`",
        "Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.",
        "",
        "| action | id | calibration | instruction (first 100 chars) | expected tools |",
        "|---|---|---|---|---|",
    ]
    for d in sorted(draft_dirs, key=lambda p: p.name):
        cal = calibration.get(d.name, {"class": "?", "detail": ""})
        instr = (d / "instruction.md").read_text().strip().replace("|", "/")[:100]
        try:
            tools = ", ".join(_read_toml(d / "task.toml").get("expected", {}).get("tools", []))
        except Exception:  # noqa: BLE001
            tools = "(parse error)"
        action = "DROP" if (d.name in dup_ids or cal["class"] == "broken") else "KEEP"
        lines.append(f"| {action} | {d.name} | {cal['class']} | {instr} | {tools} |")
    if dups:
        lines += ["", "## Near-duplicates auto-marked DROP", ""]
        lines += [f"- {a} ≈ {b} (cos {s})" for a, b, s in dups]
    sheet = domain_dir / "REVIEW.md"
    sheet.write_text("\n".join(lines) + "\n")
    return sheet
