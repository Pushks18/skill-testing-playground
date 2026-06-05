# eval/export_skill.py
"""Export travel-agent skills to Claude Code format.

Usage:
    python -m eval.export_skill --all --target ~/.claude/skills/
    python -m eval.export_skill --skill flight-search --target /tmp/x
    python -m eval.export_skill --list
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from eval.skill_loader import LoadedSkill, load_skill

# Default skills root relative to this file's location (../travel-agent-skills/skills)
_DEFAULT_SKILLS_ROOT = (
    Path(__file__).parent.parent.parent / "travel-agent-skills" / "skills"
)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _discover_skills(skills_root: Path) -> list[tuple[str, Path]]:
    """Return (export_name, skill_dir) pairs for all exportable skills.

    Top-level dirs with SKILL.md are direct skills.
    Top-level dirs WITHOUT SKILL.md but containing sub-dirs with SKILL.md
    are nested suites — each sub-skill is exported individually, named by
    its sub-dir name.

    Dirs with neither SKILL.md nor sub-skills with SKILL.md are skipped.
    """
    results: list[tuple[str, Path]] = []
    if not skills_root.exists():
        return results

    for entry in sorted(skills_root.iterdir()):
        if not entry.is_dir():
            continue
        if (entry / "SKILL.md").exists():
            # Direct skill
            results.append((entry.name, entry))
        else:
            # Check one level down for nested suite
            for sub in sorted(entry.iterdir()):
                if sub.is_dir() and (sub / "SKILL.md").exists():
                    results.append((sub.name, sub))

    return results


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def _export_one(
    skill_name: str,
    skill_dir: Path,
    target: Path,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Export a single skill directory to <target>/<skill_name>/.

    Returns (success, message).
    """
    loaded: LoadedSkill | None = load_skill(skill_dir)
    if loaded is None:
        return False, f"  SKIP {skill_name}: load_skill returned None"

    dest = target / skill_name
    if dest.exists() and not force:
        return False, f"  SKIP {skill_name}: target exists (use --force to overwrite)"

    if dry_run:
        return True, f"  {skill_name}  ({skill_dir})"

    dest.mkdir(parents=True, exist_ok=True)

    # Write SKILL.md AS-IS from source
    skill_md_src = loaded.raw_path  # points to the actual SKILL.md file
    (dest / "SKILL.md").write_bytes(skill_md_src.read_bytes())

    # Write metadata.json
    metadata = {
        "name": loaded.name,
        "description": loaded.description,
        "version": loaded.version,
        "author": loaded.author,
        "source": "travel-agent-skills",
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    (dest / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return True, f"  exported {skill_name}  →  {dest}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eval.export_skill",
        description="Export travel-agent skills to Claude Code format.",
    )
    p.add_argument(
        "--skills-root",
        type=Path,
        default=_DEFAULT_SKILLS_ROOT,
        help="Root of the skills tree (default: ../travel-agent-skills/skills)",
    )
    p.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Destination directory for exported skills.",
    )
    p.add_argument(
        "--all",
        action="store_true",
        dest="export_all",
        help="Export every skill found under --skills-root.",
    )
    p.add_argument(
        "--skill",
        metavar="NAME",
        default=None,
        help="Export a single skill by name.",
    )
    p.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="List skills that would be exported without writing anything.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing target skill directories.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    skills_root: Path = args.skills_root.expanduser().resolve()
    discovered = _discover_skills(skills_root)

    # --list: just print what would be exported
    if args.list_only:
        if not discovered:
            print("No skills found under", skills_root)
            return 0
        print(f"Skills that would be exported ({len(discovered)}):")
        for name, path in discovered:
            print(f"  {name}  ({path})")
        return 0

    # Require --target for actual export
    if args.target is None:
        print("ERROR: --target is required for export (use --list to preview).", file=sys.stderr)
        return 1

    target: Path = args.target.expanduser().resolve()

    # Safety: refuse if target is inside skills_root
    try:
        target.relative_to(skills_root)
        print(
            f"ERROR: --target ({target}) is inside --skills-root ({skills_root}). "
            "Refusing to export into the source tree.",
            file=sys.stderr,
        )
        return 1
    except ValueError:
        pass  # target is NOT inside skills_root — good

    # Determine which skills to export
    if args.export_all:
        to_export = discovered
    elif args.skill:
        to_export = [(n, p) for n, p in discovered if n == args.skill]
        if not to_export:
            print(f"ERROR: skill '{args.skill}' not found under {skills_root}.", file=sys.stderr)
            return 1
    else:
        print("ERROR: specify --all or --skill NAME.", file=sys.stderr)
        return 1

    # Export
    target.mkdir(parents=True, exist_ok=True)
    ok_count = 0
    for skill_name, skill_dir in to_export:
        success, msg = _export_one(skill_name, skill_dir, target, force=args.force)
        print(msg)
        if success:
            ok_count += 1

    print(f"\nDone: {ok_count}/{len(to_export)} skill(s) exported to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
