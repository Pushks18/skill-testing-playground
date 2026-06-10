# eval/optimizer/archive.py
"""Archive: append-only JSONL store of optimizer candidates with ε-greedy parent selection.

Slice 4 component. Stores every meaningful candidate from each optimizer run
(initial artifact, accepted steps, final best) with scores, embeddings, and
lineage (parent_hash). pick_parent() implements population-based search:
ε-greedy between the live artifact and the best archived candidate.

Default path: eval/optimizer_output/archive.jsonl
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import random
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


DEFAULT_ARCHIVE_PATH = pathlib.Path("eval/optimizer_output/archive.jsonl")

_DIVERSITY_LAMBDA = 0.3  # weight on cos-sim penalty in pick_parent scoring

# Wall-clock budget for one embedding call (model load included). Embeddings
# only feed the diversity penalty in pick_parent, so timing out degrades to
# no-embed instead of stalling a whole optimizer batch.
EMBED_TIMEOUT_S = float(os.environ.get("ARCHIVE_EMBED_TIMEOUT", "120"))


@dataclass
class ArchiveEntry:
    entry_id: str
    run_tag: str
    target: str                      # "harness:base_system_prompt" | "skill:<name>"
    layer: str                       # cluster layer (e.g. "harness:base_prompt")
    strategy: str                    # bandit arm used
    content_hash: str                # sha256 of artifact_text
    artifact_text: str               # the candidate text itself
    parent_hash: Optional[str]       # hash of the artifact this was derived from
    selection_score: Optional[float]
    test_score: Optional[float]      # only for promoted/final candidates
    accepted: bool                   # did the trainer gate accept it
    embedding: list[float]           # all-MiniLM-L6-v2 (384-d); [] when no_embed=True
    created_at: str                  # ISO-8601 UTC

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "run_tag": self.run_tag,
            "target": self.target,
            "layer": self.layer,
            "strategy": self.strategy,
            "content_hash": self.content_hash,
            "artifact_text": self.artifact_text,
            "parent_hash": self.parent_hash,
            "selection_score": self.selection_score,
            "test_score": self.test_score,
            "accepted": self.accepted,
            "embedding": self.embedding,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ArchiveEntry":
        return cls(
            entry_id=d["entry_id"],
            run_tag=d["run_tag"],
            target=d["target"],
            layer=d["layer"],
            strategy=d["strategy"],
            content_hash=d["content_hash"],
            artifact_text=d["artifact_text"],
            parent_hash=d.get("parent_hash"),
            selection_score=d.get("selection_score"),
            test_score=d.get("test_score"),
            accepted=bool(d.get("accepted", False)),
            embedding=d.get("embedding", []),
            created_at=d["created_at"],
        )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


_model = None
_model_lock = threading.Lock()


def _load_model():
    """Load all-MiniLM-L6-v2 once per process, preferring the local HF cache.

    A fresh SentenceTransformer() hits the Hugging Face Hub to check for
    updates even when the model is cached; a stalled connection there froze
    a whole optimizer batch for hours. local_files_only=True skips the
    network entirely; the online fallback gets a bounded download timeout.
    """
    global _model
    with _model_lock:
        if _model is None:
            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
            from sentence_transformers import SentenceTransformer
            try:
                _model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
            except Exception:
                _model = SentenceTransformer("all-MiniLM-L6-v2")
        return _model


def _embed(text: str) -> list[float]:
    """all-MiniLM-L6-v2 embedding, bounded by EMBED_TIMEOUT_S wall-clock.

    Runs in a daemon thread so a hung model load/download can never block the
    optimizer; on timeout or failure returns [] (entry degrades to no-embed,
    which pick_parent already handles).
    """
    result: list[list[float]] = []

    def _worker():
        try:
            model = _load_model()
            result.append(model.encode([text], normalize_embeddings=True).tolist()[0])
        except Exception as e:
            print(f"[archive] embedding failed ({type(e).__name__}: {e}) — storing entry without embedding")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(EMBED_TIMEOUT_S)
    if t.is_alive():
        print(f"[archive] embedding timed out after {EMBED_TIMEOUT_S:.0f}s — storing entry without embedding")
        return []
    return result[0] if result else []


def _cos(a: list[float], b: list[float]) -> float:
    """Cosine similarity (vectors assumed normalized by MiniLM)."""
    if not a or not b:
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(y * y for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


class Archive:
    """Append-only JSONL archive of ArchiveEntry records.

    Thread-safety: single-process only (no file locking). Each optimizer run
    appends its own entries at the end of a run — concurrent runs would
    interleave lines, which JSONL handles gracefully (each line is self-contained).
    """

    def __init__(
        self,
        path: pathlib.Path | str = DEFAULT_ARCHIVE_PATH,
        no_embed: bool = False,
    ):
        self.path = pathlib.Path(path)
        self.no_embed = no_embed

    # ── internal helpers ────────────────────────────────────────────────────

    def _load_all(self) -> list[ArchiveEntry]:
        if not self.path.exists():
            return []
        entries: list[ArchiveEntry] = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(ArchiveEntry.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                pass  # tolerate corrupt lines
        return entries

    # ── public API ──────────────────────────────────────────────────────────

    def add(self, entry: ArchiveEntry) -> bool:
        """Append entry to the JSONL file.

        Skips exact content-hash duplicates for the same target.
        Returns True if the entry was written, False if it was a duplicate.
        """
        existing = self._load_all()
        for e in existing:
            if e.target == entry.target and e.content_hash == entry.content_hash:
                return False  # exact duplicate — skip

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return True

    def entries(self, target: str | None = None) -> list[ArchiveEntry]:
        """Return all entries, optionally filtered by target."""
        all_entries = self._load_all()
        if target is None:
            return all_entries
        return [e for e in all_entries if e.target == target]

    def pick_parent(
        self,
        target: str,
        current_text: str,
        epsilon: float = 0.2,
        seed: int | None = None,
    ) -> tuple[str, str]:
        """ε-greedy parent selection.

        With probability 1−ε: return (current_text, "live") — the safety anchor.
        With probability ε:   return the best archived entry for this target,
                              scored by (selection_score − λ·cos_sim(embedding, current_embedding)),
                              i.e. high-scoring AND different from current.
                              Falls back to "live" if archive is empty.

        Returns (artifact_text, seed_source) where seed_source is "live" or
        f"archive:{entry_id}".
        """
        rng = random.Random(seed)
        target_entries = [
            e for e in self.entries(target)
            if e.selection_score is not None
        ]

        if not target_entries or rng.random() >= epsilon:
            return current_text, "live"

        # Score each candidate: selection_score − λ·cos_sim(embedding, current_embedding)
        if self.no_embed:
            # Pure score pick (no diversity penalty)
            best = max(target_entries, key=lambda e: e.selection_score or 0.0)
        else:
            current_emb = _embed(current_text)
            def _score(e: ArchiveEntry) -> float:
                sel = e.selection_score or 0.0
                sim = _cos(e.embedding, current_emb) if e.embedding else 0.0
                return sel - _DIVERSITY_LAMBDA * sim

            best = max(target_entries, key=_score)

        return best.artifact_text, f"archive:{best.entry_id}"


def make_entry(
    *,
    run_tag: str,
    target: str,
    layer: str,
    strategy: str,
    artifact_text: str,
    parent_hash: str | None = None,
    selection_score: float | None = None,
    test_score: float | None = None,
    accepted: bool = False,
    no_embed: bool = False,
) -> ArchiveEntry:
    """Factory that computes entry_id, content_hash, embedding, and created_at."""
    content_hash = _sha256(artifact_text)
    embedding = [] if no_embed else _embed(artifact_text)
    return ArchiveEntry(
        entry_id=str(uuid.uuid4()),
        run_tag=run_tag,
        target=target,
        layer=layer,
        strategy=strategy,
        content_hash=content_hash,
        artifact_text=artifact_text,
        parent_hash=parent_hash,
        selection_score=selection_score,
        test_score=test_score,
        accepted=accepted,
        embedding=embedding,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
