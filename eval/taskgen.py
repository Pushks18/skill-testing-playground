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


GENERATION_PROMPT = """You are writing evaluation tasks for an AI travel agent.

Domain: {domain}
The agent has EXACTLY these tools (use no others):
{tools}

Existing task instructions in this domain (do NOT duplicate any of these; vary
intent AND surface form):
{existing}

Write {count} NEW tasks as a JSON array. Each element:
  "id_suffix": three-digit string, starting at "{start}", incrementing
  "instruction": the user's message to the agent (realistic, specific, 1-3 sentences)
  "verifier": "tool_call_check" when success = specific tool calls, else "llm_judge"
  "tools": required tool names for tool_call_check (subset of the list above; [] for llm_judge)
  "required_params": optional {{tool: [param,...]}} for tool_call_check
  "criteria": required for llm_judge — one sentence describing a correct answer

Diversity requirements (spread across the batch):
- paraphrase families: at least 2 pairs sharing intent with different wording
- at least 2 missing-info cases where the agent should ask a question, not act
- at least 2 multi-step tasks needing 2+ tool calls in sequence
- vary named entities (cities, booking refs like BK3X9Z2A, dates, service types)

Output ONLY the JSON array. No markdown fences.
{domain_note}"""

DOMAIN_NOTES = {
    "disruption": ("Domain note: disruption = cancelled/delayed flights, rebooking, "
                   "compensation. Compose EXISTING tools (search_flights+modify_booking "
                   "for rebooking; cancel_booking+get_fare_rules for cancellations; "
                   "llm_judge for compensation/policy advice)."),
}


def parse_generated_tasks(llm_output: str, domain: str, out_dir: pathlib.Path) -> list[pathlib.Path]:
    """Write LLM-drafted tasks to draft dirs. Returns the dirs created."""
    _, weight, prefix = DOMAIN_TARGETS[domain]
    skill = DOMAIN_SKILL[domain]
    items = json.loads(llm_output)
    created: list[pathlib.Path] = []
    for item in items:
        task_id = f"{prefix}-{item['id_suffix']}"
        d = out_dir / task_id
        d.mkdir(parents=True, exist_ok=True)
        lines = [
            "[task]",
            f'id = "{task_id}"',
            f'domain = "{domain}"',
            f'skill = "{skill}"',
            f'verifier = "{item["verifier"]}"',
            f"weight = {weight}",
            "",
            "[expected]",
        ]
        if item["verifier"] == "tool_call_check":
            lines.append(f'tools = {json.dumps(item.get("tools", []))}')
            rp = item.get("required_params") or {}
            if rp:
                inner = ", ".join(f'{t} = {json.dumps(ps)}' for t, ps in rp.items())
                lines.append(f"required_params = {{ {inner} }}")
        else:
            lines.append('tools = []')
            lines.append(f'criteria = {json.dumps(item.get("criteria", ""))}')
        (d / "task.toml").write_text("\n".join(lines) + "\n")
        (d / "instruction.md").write_text(item["instruction"].strip() + "\n")
        created.append(d)
    return created


def _existing_instructions(domain: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for td in sorted(TASKS_DIR.iterdir()):
        toml_path, instr = td / "task.toml", td / "instruction.md"
        if not (toml_path.exists() and instr.exists()):
            continue
        m = re.search(r'^domain\s*=\s*"([^"]+)"', toml_path.read_text(), re.MULTILINE)
        if m and m.group(1) == domain:
            out[td.name] = instr.read_text().strip()
    return out


def _next_suffix(domain: str) -> int:
    _, _, prefix = DOMAIN_TARGETS[domain]
    nums = [int(m.group(1)) for td in TASKS_DIR.iterdir()
            if (m := re.fullmatch(rf"{re.escape(prefix)}-(\d+)", td.name))]
    return max(nums, default=0) + 1 if max(nums, default=0) >= 100 else 101


def generate_domain(domain: str, count: int | None = None) -> list[pathlib.Path]:
    """Draft `count` tasks for a domain via gpt-4o. Drafts only — no gate passed yet."""
    import openai
    target_count, _, _ = DOMAIN_TARGETS[domain]
    count = count or target_count
    existing = _existing_instructions(domain)
    prompt = GENERATION_PROMPT.format(
        domain=domain,
        tools="\n".join(f"- {t}" for t in sorted(VALID_TOOLS)),
        existing="\n".join(f"- {v}" for v in existing.values()) or "(none yet)",
        count=count,
        start=f"{_next_suffix(domain):03d}",
        domain_note=DOMAIN_NOTES.get(domain, ""),
    )
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model="gpt-4o", max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    out_dir = DRAFTS_DIR / domain
    return parse_generated_tasks(resp.choices[0].message.content.strip(), domain, out_dir)


def promote_domain(domain_dir: pathlib.Path) -> list[str]:
    """Gate 4: move KEEP rows of the human-reviewed sheet into tasks/."""
    import shutil
    sheet = domain_dir / "REVIEW.md"
    if not sheet.exists():
        sys.exit(f"promote: no REVIEW.md in {domain_dir} — run the gates and review first")
    keep: list[str] = []
    for line in sheet.read_text().splitlines():
        m = re.match(r"\|\s*(KEEP|DROP)\s*\|\s*(\S+)\s*\|", line)
        if m and m.group(1) == "KEEP":
            keep.append(m.group(2))
    promoted: list[str] = []
    for task_id in keep:
        src = domain_dir / task_id
        if not src.is_dir():
            print(f"promote: WARNING — KEEP row {task_id} has no draft dir, skipping")
            continue
        errors = validate_draft(src)
        if errors:
            print(f"promote: WARNING — {task_id} fails validation, skipping: {errors}")
            continue
        dst = TASKS_DIR / task_id
        if dst.exists():
            print(f"promote: WARNING — {task_id} already in tasks/, skipping")
            continue
        shutil.copytree(src, dst)
        promoted.append(task_id)
    print(f"promoted {len(promoted)}/{len(keep)} KEEP rows from {domain_dir.name}")
    return promoted


def main() -> None:
    parser = argparse.ArgumentParser(description="Task bank expansion pipeline.")
    parser.add_argument("command", choices=["generate", "validate", "dedupe", "calibrate", "review-sheet", "promote"])
    parser.add_argument("--domain", required=True, choices=sorted(DOMAIN_TARGETS))
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--mock-mcp-url", default="http://localhost:8000")
    parser.add_argument("--threshold", type=float, default=0.90)
    args = parser.parse_args()

    domain_dir = DRAFTS_DIR / args.domain
    drafts = sorted(d for d in domain_dir.iterdir() if d.is_dir()) if domain_dir.exists() else []

    if args.command == "generate":
        created = generate_domain(args.domain, args.count)
        print(f"drafted {len(created)} tasks → {domain_dir}")
    elif args.command == "validate":
        all_errors = [e for d in drafts for e in validate_draft(d)]
        print("\n".join(all_errors) if all_errors else f"all {len(drafts)} drafts structurally valid")
        sys.exit(1 if all_errors else 0)
    elif args.command == "dedupe":
        draft_texts = {d.name: (d / "instruction.md").read_text().strip() for d in drafts}
        dups = find_near_duplicates(draft_texts, _existing_instructions(args.domain), args.threshold)
        (domain_dir / "dups.json").write_text(json.dumps(dups, indent=2))
        print(f"{len(dups)} near-duplicates flagged" + (f": {dups}" if dups else ""))
    elif args.command == "calibrate":
        report = calibrate_drafts(drafts, args.mock_mcp_url)
        (domain_dir / "calibration.json").write_text(json.dumps(report, indent=2))
        counts: dict[str, int] = {}
        for v in report.values():
            counts[v["class"]] = counts.get(v["class"], 0) + 1
        print(f"calibration: {counts}")
    elif args.command == "review-sheet":
        report = json.loads((domain_dir / "calibration.json").read_text())
        dups = [tuple(x) for x in json.loads((domain_dir / "dups.json").read_text())]
        sheet = write_review_sheet(domain_dir, drafts, report, dups)
        print(f"review sheet: {sheet}")
    elif args.command == "promote":
        promote_domain(domain_dir)


if __name__ == "__main__":
    main()
