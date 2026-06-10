#!/usr/bin/env python3
"""Drive the taskgen pipeline until each domain's bank reaches a target count.

Runs the repo's own four gates per batch — generate → validate → dedupe →
calibrate → review-sheet (auto-DROPs dups/broken) → promote (re-validates,
skips collisions). Deterministic replacement for the flaky subagent runs:
every step is logged, stale drafts are archived first, and a stall in one
batch can't silently eat the whole expansion.

Usage:
    python scripts/expand_bank.py --domains flight_search hotel_search --target 50
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DRAFTS = REPO / "tasks_drafts"
TASKS = REPO / "tasks"
PY = sys.executable

# edge_cases generates edge-mixed-* but the bank counts all edge-* families
COUNT_PREFIX = {"edge_cases": "edge-"}

BATCH = 10
MAX_ROUNDS = 12


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def bank_count(prefix: str) -> int:
    return sum(1 for d in TASKS.iterdir() if d.name.startswith(prefix))


def run(cmd: list[str]) -> int:
    log("$ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=REPO, timeout=3600)
    return r.returncode


def archive_drafts(domain: str) -> None:
    """Move leftover draft task dirs + gate artifacts out of the way."""
    dom_dir = DRAFTS / domain
    if not dom_dir.exists():
        return
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = DRAFTS / "_archive" / f"{domain}_{stamp}"
    moved = False
    for entry in list(dom_dir.iterdir()):
        if entry.is_dir() or entry.name in ("REVIEW.md", "calibration.json", "dups.json"):
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(entry), str(dest / entry.name))
            moved = True
    if moved:
        log(f"archived stale drafts → {dest}")


def expand(domain: str, target: int, prefix: str, mock_url: str) -> bool:
    count_prefix = COUNT_PREFIX.get(domain, prefix)
    archive_drafts(domain)
    for round_no in range(1, MAX_ROUNDS + 1):
        have = bank_count(count_prefix)
        if have >= target:
            log(f"{domain}: target reached ({have}/{target})")
            return True
        need = min(BATCH, target - have)
        log(f"{domain}: round {round_no} — bank {have}/{target}, generating {need}")
        base = [PY, "-m", "eval.taskgen", "--domain", domain]
        if run(base + ["generate", "--count", str(need)]) != 0:
            log(f"{domain}: generate failed, stopping domain")
            return False
        run(base + ["validate"])  # promote re-validates; bad drafts get skipped there
        for stage in ("dedupe", "calibrate", "review-sheet", "promote"):
            cmd = base + [stage]
            if stage == "calibrate":
                cmd += ["--mock-mcp-url", mock_url]
            if run(cmd) != 0:
                log(f"{domain}: {stage} failed, stopping domain")
                return False
        archive_drafts(domain)
    log(f"{domain}: hit MAX_ROUNDS={MAX_ROUNDS} before target — bank at {bank_count(count_prefix)}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domains", nargs="+", required=True)
    parser.add_argument("--target", type=int, default=50)
    parser.add_argument("--mock-mcp-url", default="http://localhost:8000")
    args = parser.parse_args()

    sys.path.insert(0, str(REPO))
    from eval.taskgen import DOMAIN_TARGETS  # late import: validates domain names

    ok = True
    for domain in args.domains:
        if domain not in DOMAIN_TARGETS:
            sys.exit(f"unknown domain {domain!r} (choices: {sorted(DOMAIN_TARGETS)})")
        prefix = DOMAIN_TARGETS[domain][2]
        ok = expand(domain, args.target, prefix, args.mock_mcp_url) and ok
    log("ALL DONE" if ok else "FINISHED WITH FAILURES")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
