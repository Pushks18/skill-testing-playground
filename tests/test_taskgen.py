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
