#!/usr/bin/env python3
"""Detect which skill was changed in this PR and print its directory path."""
import subprocess
import pathlib
import sys

result = subprocess.run(
    ["git", "diff", "--name-only", "HEAD^1", "HEAD"],
    capture_output=True, text=True,
)
changed = result.stdout.strip().split("\n")
for path in changed:
    if "skills/" in path and "SKILL.md" in path:
        p = pathlib.Path(path)
        print(str(p.parent))
        sys.exit(0)

print("")
sys.exit(0)
