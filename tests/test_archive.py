# tests/test_archive.py
"""Tests for eval/optimizer/archive.py — all heavy I/O and embeddings stubbed."""
from __future__ import annotations

import json
import pathlib

import pytest

from eval.optimizer.archive import (
    Archive,
    ArchiveEntry,
    _sha256,
    make_entry,
)

TARGET = "harness:base_system_prompt"
LAYER = "harness:base_prompt"
STRATEGY = "push-tool-action"


def _entry(
    artifact_text: str = "Hello world",
    target: str = TARGET,
    selection_score: float = 0.8,
    accepted: bool = True,
    embedding: list[float] | None = None,
    run_tag: str = "run_001",
) -> ArchiveEntry:
    return ArchiveEntry(
        entry_id="test-uuid",
        run_tag=run_tag,
        target=target,
        layer=LAYER,
        strategy=STRATEGY,
        content_hash=_sha256(artifact_text),
        artifact_text=artifact_text,
        parent_hash=None,
        selection_score=selection_score,
        test_score=None,
        accepted=accepted,
        embedding=embedding if embedding is not None else [],
        created_at="2026-06-05T00:00:00+00:00",
    )


# ── add + entries roundtrip ──────────────────────────────────────────────────

def test_add_and_entries_roundtrip(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    e1 = _entry("artifact A")
    e2 = _entry("artifact B")
    archive.add(e1)
    archive.add(e2)
    results = archive.entries()
    assert len(results) == 2
    texts = {r.artifact_text for r in results}
    assert texts == {"artifact A", "artifact B"}


def test_entries_filter_by_target(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    e1 = _entry("artifact A", target="harness:base_system_prompt")
    e2 = _entry("artifact B", target="skill:flight-search")
    archive.add(e1)
    archive.add(e2)
    filtered = archive.entries(target="skill:flight-search")
    assert len(filtered) == 1
    assert filtered[0].artifact_text == "artifact B"


def test_entries_empty_archive(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    assert archive.entries() == []


# ── content-hash dedupe ──────────────────────────────────────────────────────

def test_content_hash_dedupe_same_target(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    e1 = _entry("same text", target=TARGET)
    e2 = _entry("same text", target=TARGET)  # same text = same hash
    r1 = archive.add(e1)
    r2 = archive.add(e2)
    assert r1 is True
    assert r2 is False  # duplicate skipped
    assert len(archive.entries()) == 1


def test_content_hash_dedupe_different_target_not_deduped(tmp_path):
    """Same text but different target should NOT be deduped."""
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    e1 = _entry("same text", target="harness:base_system_prompt")
    e2 = _entry("same text", target="skill:flight-search")
    r1 = archive.add(e1)
    r2 = archive.add(e2)
    assert r1 is True
    assert r2 is True
    assert len(archive.entries()) == 2


# ── pick_parent epsilon=0 returns live ──────────────────────────────────────

def test_pick_parent_epsilon_zero_returns_live(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    archive.add(_entry("archived text", selection_score=0.9))
    text, source = archive.pick_parent(TARGET, "live text", epsilon=0.0, seed=42)
    assert text == "live text"
    assert source == "live"


# ── pick_parent epsilon=1 with no_embed picks highest selection_score ────────

def test_pick_parent_epsilon_one_no_embed_picks_best_score(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    e_low = _entry("artifact low", selection_score=0.3)
    e_high = _entry("artifact high", selection_score=0.9)
    e_mid = _entry("artifact mid", selection_score=0.6)
    archive.add(e_low)
    archive.add(e_high)
    archive.add(e_mid)

    # With epsilon=1, always picks from archive; seed=0 always draws < 1.0
    text, source = archive.pick_parent(TARGET, "current", epsilon=1.0, seed=0)
    assert text == "artifact high"
    assert source.startswith("archive:")


def test_pick_parent_epsilon_one_empty_archive_returns_live(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    text, source = archive.pick_parent(TARGET, "live text", epsilon=1.0, seed=0)
    assert text == "live text"
    assert source == "live"


def test_pick_parent_epsilon_one_no_score_entries_returns_live(tmp_path):
    """Entries without selection_score are excluded from candidate pool."""
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    e = _entry("artifact A", selection_score=None)
    e2 = ArchiveEntry(
        entry_id="x",
        run_tag="r",
        target=TARGET,
        layer=LAYER,
        strategy=STRATEGY,
        content_hash=_sha256("artifact A"),
        artifact_text="artifact A",
        parent_hash=None,
        selection_score=None,
        test_score=None,
        accepted=False,
        embedding=[],
        created_at="2026-06-05T00:00:00+00:00",
    )
    archive.add(e2)
    text, source = archive.pick_parent(TARGET, "live text", epsilon=1.0, seed=0)
    assert text == "live text"
    assert source == "live"


# ── JSONL file format stability ──────────────────────────────────────────────

def test_jsonl_file_format(tmp_path):
    archive_path = tmp_path / "archive.jsonl"
    archive = Archive(path=archive_path, no_embed=True)
    e = _entry("artifact text")
    archive.add(e)

    lines = archive_path.read_text().strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["artifact_text"] == "artifact text"
    assert parsed["target"] == TARGET
    assert "entry_id" in parsed
    assert "content_hash" in parsed
    assert "created_at" in parsed


def test_jsonl_multiple_entries_one_per_line(tmp_path):
    archive_path = tmp_path / "archive.jsonl"
    archive = Archive(path=archive_path, no_embed=True)
    for i in range(5):
        archive.add(_entry(f"artifact {i}"))
    lines = archive_path.read_text().strip().splitlines()
    assert len(lines) == 5
    for line in lines:
        obj = json.loads(line)
        assert "artifact_text" in obj


def test_jsonl_corrupt_line_tolerated(tmp_path):
    archive_path = tmp_path / "archive.jsonl"
    # Write one valid + one corrupt line manually
    e = _entry("artifact A")
    archive_path.write_text(
        json.dumps(e.to_dict()) + "\n"
        + "not-valid-json\n"
    )
    archive = Archive(path=archive_path, no_embed=True)
    results = archive.entries()
    assert len(results) == 1  # corrupt line skipped


# ── make_entry factory (no_embed=True) ──────────────────────────────────────

def test_make_entry_no_embed(tmp_path):
    entry = make_entry(
        run_tag="run_test",
        target=TARGET,
        layer=LAYER,
        strategy=STRATEGY,
        artifact_text="Test artifact",
        selection_score=0.75,
        accepted=True,
        no_embed=True,
    )
    assert entry.embedding == []
    assert entry.content_hash == _sha256("Test artifact")
    assert entry.run_tag == "run_test"
    assert entry.accepted is True
    assert entry.selection_score == 0.75


def test_make_entry_roundtrip_via_archive(tmp_path):
    archive = Archive(path=tmp_path / "archive.jsonl", no_embed=True)
    entry = make_entry(
        run_tag="run_x",
        target=TARGET,
        layer=LAYER,
        strategy="simplify",
        artifact_text="Some skill content here",
        parent_hash="abc123",
        selection_score=0.5,
        test_score=0.6,
        accepted=False,
        no_embed=True,
    )
    archive.add(entry)
    loaded = archive.entries()[0]
    assert loaded.artifact_text == "Some skill content here"
    assert loaded.parent_hash == "abc123"
    assert loaded.test_score == 0.6
    assert loaded.accepted is False
    assert loaded.embedding == []


# ── _embed degradation (timeout / failure must never hang the optimizer) ─────

def test_embed_returns_empty_on_load_failure(monkeypatch):
    import eval.optimizer.archive as archive_mod

    def _boom():
        raise RuntimeError("model load failed")

    monkeypatch.setattr(archive_mod, "_load_model", _boom)
    assert archive_mod._embed("some text") == []


def test_embed_returns_empty_on_timeout(monkeypatch):
    import time
    import eval.optimizer.archive as archive_mod

    def _hang():
        time.sleep(5)

    monkeypatch.setattr(archive_mod, "_load_model", _hang)
    monkeypatch.setattr(archive_mod, "EMBED_TIMEOUT_S", 0.2)
    start = time.monotonic()
    assert archive_mod._embed("some text") == []
    assert time.monotonic() - start < 2


def test_make_entry_degrades_to_no_embedding(monkeypatch):
    import eval.optimizer.archive as archive_mod

    def _boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(archive_mod, "_load_model", _boom)
    entry = make_entry(
        run_tag="run_x", target=TARGET, layer=LAYER, strategy="simplify",
        artifact_text="content", no_embed=False,
    )
    assert entry.embedding == []
