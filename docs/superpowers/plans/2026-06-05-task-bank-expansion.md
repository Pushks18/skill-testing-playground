# Task Bank Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the task bank 73 → ~141 via LLM-drafted, 4-gate-QC'd, human-approved tasks per the focused-doubling targets, including the new `disruption` domain.

**Architecture:** One new module `eval/taskgen.py` with subcommands (`generate`, `validate`, `dedupe`, `calibrate`, `promote`) operating on a staging dir `tasks_drafts/`. Nothing reaches `tasks/` without passing structural validation, embedding dedupe, a single-trial no_skill calibration, and human review of a per-domain REVIEW.md sheet.

**Tech Stack:** Python 3.11, existing OpenAI client pattern (gpt-4o for drafting), sentence-transformers MiniLM (already in stack), tomllib, pytest.

**Spec:** `docs/superpowers/specs/2026-06-05-task-bank-expansion-design.md`

---

## Execution preamble

- Repo: `/Users/pushkaraj/Documents/skill-testing-playground`, commits on main, imperative style, NO co-author lines, `git add` only your task's files (repo has unrelated drift).
- Use `.venv/bin/python` (plain `python` not on PATH).
- `tasks_drafts/` is staging — add it to `.gitignore`? NO: drafts + review sheets should be committable for the human review flow. Keep them tracked.
- Generation targets (from spec): ancillery +10, booking_flow +12, fare_rules +10, itinerary_build +10, disruption +12, edge_cases +6, flight_search +4, trip_planning +4.
- task.toml format (copy existing): `[task]` id/domain/skill/verifier/weight + `[expected]` tools (+ optional required_params). Skill mapping: ancillery→ancillery-skill, booking_flow→booking-skill, fare_rules→fare-rules, itinerary_build→planning-skill, trip_planning→planning-skill, flight_search→flight-search, edge_cases→modify-booking, hotel_search→hotel-search, disruption→disruption-handling (does not exist yet — intentional).
- The 10 mock tools (the ONLY valid `expected.tools` values): search_flights, search_hotels, check_availability, get_fare_rules, validate_passenger, create_booking, modify_booking, cancel_booking, get_itinerary, add_ancillary.
- HUMAN GATE: execution STOPS after Task 5 (review sheets ready). Promotion (Task 6) only runs after the user reviews.

### File map

| File | Responsibility |
|---|---|
| `eval/taskgen.py` (new) | all five subcommands + prompts |
| `eval/gate_check.py` (modify) | add `"disruption": 2.0` to TASK_WEIGHTS |
| `tests/test_taskgen.py` (new) | unit tests, LLM + run_task stubbed |
| `tasks_drafts/<domain>/…` (generated) | staged drafts + REVIEW.md per domain |

---

### Task 1: taskgen skeleton + structural validation (gate 1)

**Files:** Create `eval/taskgen.py`, `tests/test_taskgen.py`

- [ ] **Step 1: failing tests** — create `tests/test_taskgen.py`:

```python
# tests/test_taskgen.py
import pathlib
import pytest

from eval.taskgen import validate_draft, VALID_TOOLS, DOMAIN_SKILL, DOMAIN_TARGETS

GOOD_TOML = '''[task]
id = "disruption-101"
domain = "disruption"
skill = "disruption-handling"
verifier = "tool_call_check"
weight = 2.0

[expected]
tools = ["search_flights", "modify_booking"]
'''


def _draft(tmp_path, task_id="disruption-101", toml=GOOD_TOML, instruction="My flight was cancelled, rebook me."):
    d = tmp_path / task_id
    d.mkdir(parents=True)
    if toml is not None:
        (d / "task.toml").write_text(toml)
    if instruction is not None:
        (d / "instruction.md").write_text(instruction)
    return d


def test_validate_good_draft(tmp_path):
    errors = validate_draft(_draft(tmp_path))
    assert errors == []


def test_validate_rejects_unknown_tool(tmp_path):
    bad = GOOD_TOML.replace('"modify_booking"', '"teleport_passenger"')
    errors = validate_draft(_draft(tmp_path, toml=bad))
    assert any("teleport_passenger" in e for e in errors)


def test_validate_rejects_id_dir_mismatch(tmp_path):
    d = _draft(tmp_path, task_id="disruption-999")   # toml says disruption-101
    errors = validate_draft(d)
    assert any("id" in e.lower() for e in errors)


def test_validate_rejects_missing_instruction(tmp_path):
    d = _draft(tmp_path, instruction=None)
    errors = validate_draft(d)
    assert any("instruction" in e.lower() for e in errors)


def test_validate_rejects_bad_verifier(tmp_path):
    bad = GOOD_TOML.replace("tool_call_check", "vibes_check")
    errors = validate_draft(_draft(tmp_path, toml=bad))
    assert any("verifier" in e.lower() for e in errors)


def test_domain_constants_consistent():
    assert set(DOMAIN_TARGETS) <= set(DOMAIN_SKILL)
    assert len(VALID_TOOLS) == 10
```

- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_taskgen.py -v` → ModuleNotFoundError

- [ ] **Step 3: implement** — create `eval/taskgen.py`:

```python
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
```

(CLI `main()` comes in Task 4 once all subcommand functions exist; keep this Task importable-only.)

- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_taskgen.py -v` → 6 PASS
- [ ] **Step 5:** commit

```bash
git add eval/taskgen.py tests/test_taskgen.py
git commit -m "feat: add taskgen structural validation gate"
```

---

### Task 2: embedding dedupe (gate 2)

**Files:** Modify `eval/taskgen.py`, `tests/test_taskgen.py`

- [ ] **Step 1: failing tests** — append:

```python
from eval.taskgen import find_near_duplicates


def test_dedupe_flags_near_identical(monkeypatch):
    # stub the embedder with a deterministic fake: identical strings → identical vecs
    import eval.taskgen as tg

    def fake_embed(texts):
        # map each text to a simple bag vector over a tiny vocab
        vocab = ["cancel", "rebook", "lounge", "seat", "flight", "hotel"]
        return [[float(t.lower().count(w)) for w in vocab] for t in texts]

    monkeypatch.setattr(tg, "_embed", fake_embed)
    existing = {"t-001": "Rebook my cancelled flight tomorrow"}
    drafts = {
        "d-001": "Rebook my cancelled flight tomorrow",       # exact dup
        "d-002": "I want lounge access and a window seat",    # distinct
    }
    dups = find_near_duplicates(drafts, existing, threshold=0.90)
    assert "d-001" in {d for d, _, _ in dups}
    assert all(d != "d-002" for d, _, _ in dups)


def test_dedupe_flags_within_batch(monkeypatch):
    import eval.taskgen as tg
    monkeypatch.setattr(tg, "_embed", lambda texts: [[1.0, 0.0]] * len(texts))
    drafts = {"d-001": "anything", "d-002": "anything else"}   # same vec → dup pair
    dups = find_near_duplicates(drafts, {}, threshold=0.90)
    assert dups  # second of the pair flagged against the first
```

- [ ] **Step 2:** run → ImportError
- [ ] **Step 3: implement** — append to `eval/taskgen.py`:

```python
def _embed(texts: list[str]) -> list[list[float]]:
    """MiniLM embeddings (lazy import — model load is slow)."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(texts, normalize_embeddings=True).tolist()


def _cos(a: list[float], b: list[float]) -> float:
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
    an existing instruction or an earlier draft in the same batch."""
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
```

- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_taskgen.py -v` → 8 PASS. Also sanity-check the real embedder loads: `.venv/bin/python -c "from eval.taskgen import _embed; print(len(_embed(['hello'])[0]))"` → 384 (sentence-transformers is expected to be installed for skill_router; if it is NOT, `pip install sentence-transformers` and note it).
- [ ] **Step 5:** commit `feat: add embedding near-duplicate gate to taskgen`

---

### Task 3: calibration (gate 3) + review sheet writer

**Files:** Modify `eval/taskgen.py`, `tests/test_taskgen.py`

- [ ] **Step 1: failing tests** — append:

```python
from eval.taskgen import calibrate_drafts, write_review_sheet


class _FakeResult:
    def __init__(self, passed, score, reason=""):
        self.passed_verifier = passed
        self.score = score
        self.judge_reasoning = reason


def test_calibrate_classifies(tmp_path, monkeypatch):
    import eval.taskgen as tg
    d1 = _draft(tmp_path / "batch", task_id="disruption-101")
    toml2 = GOOD_TOML.replace("disruption-101", "disruption-102")
    d2 = _draft(tmp_path / "batch", task_id="disruption-102", toml=toml2)

    outcomes = {"disruption-101": _FakeResult(True, 1.0),
                "disruption-102": _FakeResult(False, 0.0, "missing tool")}

    def fake_run_task(task_path, skill_path, condition, url):
        return outcomes[pathlib.Path(task_path).name]

    monkeypatch.setattr(tg, "run_task", fake_run_task)
    report = calibrate_drafts([d1, d2], mock_mcp_url="http://x")
    assert report["disruption-101"]["class"] == "baseline-pass"
    assert report["disruption-102"]["class"] == "baseline-fail"


def test_calibrate_marks_broken_on_exception(tmp_path, monkeypatch):
    import eval.taskgen as tg
    d1 = _draft(tmp_path / "b2", task_id="disruption-101")
    monkeypatch.setattr(tg, "run_task", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    report = calibrate_drafts([d1], mock_mcp_url="http://x")
    assert report["disruption-101"]["class"] == "broken"


def test_review_sheet_written(tmp_path):
    d1 = _draft(tmp_path / "b3", task_id="disruption-101")
    report = {"disruption-101": {"class": "baseline-fail", "detail": "missing tool"}}
    sheet = write_review_sheet(tmp_path / "b3", [d1], report, dups=[])
    text = sheet.read_text()
    assert "disruption-101" in text and "baseline-fail" in text
    assert "APPROVE" in text          # the action column instruction
```

- [ ] **Step 2:** run → ImportError
- [ ] **Step 3: implement** — append (and add `from eval.run_task import run_task` to imports):

```python
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
```

- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_taskgen.py -v` → 11 PASS
- [ ] **Step 5:** commit `feat: add calibration gate and human review sheet to taskgen`

---

### Task 4: generation + promote + CLI + disruption weight

**Files:** Modify `eval/taskgen.py`, `tests/test_taskgen.py`, `eval/gate_check.py`

- [ ] **Step 1: failing tests** — append:

```python
from eval.taskgen import parse_generated_tasks, promote_domain


SAMPLE_LLM_OUTPUT = '''[
  {"id_suffix": "101",
   "instruction": "My flight got cancelled due to weather. Rebook me on the next available flight to Denver.",
   "verifier": "tool_call_check",
   "tools": ["search_flights", "modify_booking"],
   "required_params": {}},
  {"id_suffix": "102",
   "instruction": "Am I entitled to compensation for my 6-hour delay on flight UA123?",
   "verifier": "llm_judge",
   "tools": [],
   "criteria": "Explains compensation eligibility accurately without fabricating policy"}
]'''


def test_parse_generated_tasks(tmp_path):
    drafts = parse_generated_tasks(SAMPLE_LLM_OUTPUT, domain="disruption", out_dir=tmp_path)
    assert len(drafts) == 2
    d = tmp_path / "disruption-101"
    meta = d / "task.toml"
    assert meta.exists() and (d / "instruction.md").exists()
    text = meta.read_text()
    assert 'domain = "disruption"' in text
    assert 'skill = "disruption-handling"' in text
    assert 'weight = 2.0' in text
    # llm_judge draft has no tools requirement
    t2 = (tmp_path / "disruption-102" / "task.toml").read_text()
    assert 'verifier = "llm_judge"' in t2


def test_promote_moves_only_keep_rows(tmp_path, monkeypatch):
    import eval.taskgen as tg
    monkeypatch.setattr(tg, "TASKS_DIR", tmp_path / "tasks")
    domain_dir = tmp_path / "drafts" / "disruption"
    d1 = _draft(domain_dir, task_id="disruption-101")
    toml2 = GOOD_TOML.replace("disruption-101", "disruption-102")
    d2 = _draft(domain_dir, task_id="disruption-102", toml=toml2)
    (domain_dir / "REVIEW.md").write_text(
        "| action | id |\n|---|---|\n"
        "| KEEP | disruption-101 |\n| DROP | disruption-102 |\n")
    promoted = promote_domain(domain_dir)
    assert (tmp_path / "tasks" / "disruption-101").exists()
    assert not (tmp_path / "tasks" / "disruption-102").exists()
    assert promoted == ["disruption-101"]


def test_promote_refuses_without_review_sheet(tmp_path, monkeypatch):
    import eval.taskgen as tg
    monkeypatch.setattr(tg, "TASKS_DIR", tmp_path / "tasks")
    domain_dir = tmp_path / "drafts2" / "disruption"
    _draft(domain_dir, task_id="disruption-101")
    with pytest.raises(SystemExit):
        promote_domain(domain_dir)
```

- [ ] **Step 2:** run → ImportError
- [ ] **Step 3: implement** — append:

```python
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
```

Also in `eval/gate_check.py`, add to TASK_WEIGHTS: `"disruption": 2.0,` (after "hotel_search").

- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_taskgen.py tests/test_gate_check.py -v` → all pass (15 taskgen + existing gate_check; note test_gate_check has 2 PRE-EXISTING failures unrelated to this — do not fix, just confirm no NEW failures)
- [ ] **Step 5:** commit

```bash
git add eval/taskgen.py tests/test_taskgen.py eval/gate_check.py
git commit -m "feat: add taskgen generation, promotion CLI, and disruption weight"
```

---

### Task 5: run the generation campaign (paid: ~$0.30 LLM drafts + ~$0.05 calibration)

**Files:** generated `tasks_drafts/**` only. Needs mock MCP on :8000 and OPENAI_API_KEY.

- [ ] **Step 1:** mock MCP up (`lsof -i :8000`, start if needed — remember if you did)
- [ ] **Step 2:** for EACH domain in (ancillery, booking_flow, fare_rules, itinerary_build, disruption, edge_cases, flight_search, trip_planning), run the full gate sequence:

```bash
.venv/bin/python -m eval.taskgen generate --domain <d>
.venv/bin/python -m eval.taskgen validate --domain <d>     # fix/regenerate on errors
.venv/bin/python -m eval.taskgen dedupe --domain <d>
.venv/bin/python -m eval.taskgen calibrate --domain <d>
.venv/bin/python -m eval.taskgen review-sheet --domain <d>
```

If `validate` fails for a draft: inspect, fix mechanically if trivial (e.g., weight format), else delete the draft dir and note it. If a generation batch comes back unparseable, retry ONCE with the same prompt; if still broken, report it.

- [ ] **Step 3:** summarize per domain: drafted / structurally-valid / dups flagged / calibration mix (pass/fail/broken). The 60/40 pass/fail target is a guideline — report the actual mix, do NOT regenerate to force it.
- [ ] **Step 4:** commit the staging area:

```bash
git add tasks_drafts/
git commit -m "feat: draft 68 candidate tasks with QC gates for human review"
```

- [ ] **Step 5: STOP.** Report the per-domain summary and the review-sheet paths. The human reviews each `tasks_drafts/<domain>/REVIEW.md` (flips KEEP→DROP, edits drafts). Task 6 runs only after their go-ahead.

---

### Task 6 (after human review): promote + verify

- [ ] **Step 1:** per domain: `.venv/bin/python -m eval.taskgen promote --domain <d>`
- [ ] **Step 2:** full structural sweep of the bank:

```bash
.venv/bin/python - <<'EOF'
import pathlib
from eval.taskgen import validate_draft
errs = [e for d in sorted(pathlib.Path("tasks").iterdir()) if d.is_dir()
        for e in validate_draft(d)]
print("\n".join(errs) if errs else "entire bank structurally valid")
EOF
```

(Pre-existing tasks may trip the id/dir or skill-mapping checks if they predate conventions — report rather than fix.)

- [ ] **Step 3:** counts vs target table; ancillery smoke `ab_compare --skill-path ../travel-agent-skills/skills/ancillery-skill --trials 2` to confirm 20-task discovery.
- [ ] **Step 4:** commit `feat: promote reviewed tasks — bank at ~141 across 9 domains`

---

## Self-review notes

- Spec coverage: generation w/ diversity directives (Task 4 prompt), 4 QC gates (Tasks 1-3 + promote-time re-validation), staging dir + human gate (Tasks 4-6), disruption weight (Task 4), verification sweep (Task 6). Out-of-scope items untouched.
- Type consistency: `validate_draft -> list[str]`, `find_near_duplicates -> list[tuple]`, `calibrate_drafts -> dict`, `write_review_sheet -> Path`, `promote_domain -> list[str]` used consistently across tasks; `_FakeResult` matches the EvalResult fields run_task consumers read.
- The human gate is structural: Task 5 ends in STOP; promote refuses without REVIEW.md.
