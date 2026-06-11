# eval/optimizer/propose_skill.py
"""Phase 6.2: Auto-propose new skills from failure clusters.

Reads failed runs from trajectory.db, clusters by domain + failure_mode,
and for any cluster exceeding the threshold with no existing skill, drafts
a SKILL.md body via LLM and opens a PR against travel-agent-skills.

Usage
─────
    # Dry run — print clusters and proposed content, no PR opened
    python -m eval.optimizer.propose_skill --dry-run

    # Open PRs for all qualifying clusters
    python -m eval.optimizer.propose_skill \
        --github-token ghp_... \
        --repo Tabhi-Commons/travel-agent-skills \
        --threshold 5

    # Target a specific domain
    python -m eval.optimizer.propose_skill --domain disruption --threshold 3
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import argparse
import base64
import json
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

PROPOSE_PROMPT = """\
You are writing a SKILL.md body for a travel agent AI system.

A cluster of {n} failed agent tasks in the "{domain}" domain has been identified.
The suggested skill name is "{skill_name}".

Here are representative failed task instructions:
{instructions}

The most common failure mode is: {failure_mode}

Write ONLY the markdown body (no YAML frontmatter). Use exactly these sections:

# {title}

## Workflow

Numbered steps. Step 1 must always be:
"**Confirm required inputs.** Ask for any missing required fields before proceeding."
Each step must address why the agent was failing on the tasks above.

## Required Inputs

A markdown table with columns: Input | Notes

## Optional Inputs

A markdown table with columns: Input | Default

## Output

What the agent must produce — structured format, required fields.

## Edge Cases and Quality Checks

Bullet list covering the specific failure patterns seen in the tasks above.

Rules:
- Be specific to "{skill_name}". No generic placeholder text.
- Never tell the agent to fabricate data or guess missing inputs.
- Keep the body under 400 lines.
- Do not include YAML frontmatter or markdown code fences.
"""

# Domain → canonical skill name (for existing skills, no new PR should be opened)
_KNOWN_SKILLS: dict[str, str] = {
    "flight_search": "flight-search",
    "hotel_search": "hotel-search",
    "booking_flow": "booking-skill",
    "fare_rules": "fare-rules",
    "edge_cases": "modify-booking",
    "itinerary_build": "planning-skill",
    "ancillery": "ancillery-skill",
}

_DOMAIN_TO_SKILL_NAME: dict[str, str] = {
    **_KNOWN_SKILLS,
    "disruption": "disruption-handling",
    "baggage": "baggage-policy",
    "loyalty": "loyalty-rewards",
    "visa": "visa-requirements",
    "insurance": "travel-insurance",
}


@dataclass
class FailureCluster:
    domain: str
    failure_mode: str
    task_ids: list[str]
    instructions: list[str]
    suggested_skill_name: str
    description: str
    n_failures: int = field(init=False)

    def __post_init__(self) -> None:
        self.n_failures = len(self.task_ids)


# ---------------------------------------------------------------------------
# Cluster failures from trajectory.db
# ---------------------------------------------------------------------------

def load_failure_clusters(
    db_path: Path,
    tasks_dir: Path,
    min_failures: int = 5,
    condition: str = "no_skill",
    existing_skills: set[str] | None = None,
) -> list[FailureCluster]:
    """
    Query trajectory.db for failed no_skill runs, cluster by domain,
    and return clusters that have no existing skill and exceed min_failures.
    """
    if not db_path.exists():
        return []

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT task_id, failure_mode FROM runs "
        "WHERE passed = 0 AND condition = ? "
        "ORDER BY rowid DESC LIMIT 500",
        (condition,),
    ).fetchall()
    con.close()

    # Group by domain (look up domain from task.toml)
    domain_tasks: dict[str, list[tuple[str, str]]] = defaultdict(list)
    task_instructions: dict[str, str] = {}

    for row in rows:
        task_id = row["task_id"]
        failure_mode = row["failure_mode"] or "UNKNOWN"
        task_dir = tasks_dir / task_id
        if not task_dir.exists():
            continue
        domain = _read_task_domain(task_dir)
        if not domain:
            continue
        instr = _read_instruction(task_dir)
        task_instructions[task_id] = instr
        domain_tasks[domain].append((task_id, failure_mode))

    clusters: list[FailureCluster] = []
    for domain, pairs in domain_tasks.items():
        if len(pairs) < min_failures:
            continue

        # Skip if a skill already exists for this domain
        skill_name = _domain_to_skill_name(domain)
        if existing_skills and skill_name in existing_skills:
            continue

        # Dominant failure mode
        mode_counts: dict[str, int] = defaultdict(int)
        for _, fm in pairs:
            mode_counts[fm] += 1
        dominant_mode = max(mode_counts, key=mode_counts.get)

        task_ids = [t for t, _ in pairs]
        instructions = [task_instructions[t] for t in task_ids if t in task_instructions]

        clusters.append(FailureCluster(
            domain=domain,
            failure_mode=dominant_mode,
            task_ids=task_ids,
            instructions=instructions[:5],
            suggested_skill_name=skill_name,
            description=_auto_description(skill_name, domain),
        ))

    return clusters


def load_clusters_from_ab_results(
    ab_results_path: Path,
    tasks_dir: Path,
    min_failures: int = 3,
    existing_skills: set[str] | None = None,
) -> list[FailureCluster]:
    """
    Read ab_results.json for tasks where no_skill.score < 0.4 (agent fails without skill),
    cluster by domain, and propose skills for uncovered domains.
    """
    if not ab_results_path.exists():
        return []

    data = json.loads(ab_results_path.read_text())
    tasks_data = data.get("tasks", [])

    domain_tasks: dict[str, list[dict]] = defaultdict(list)
    for task in tasks_data:
        no_skill = task.get("no_skill", {})
        if no_skill.get("score", 1.0) >= 0.4:
            continue
        domain = no_skill.get("domain", "unknown")
        domain_tasks[domain].append(task)

    clusters: list[FailureCluster] = []
    for domain, tasks in domain_tasks.items():
        if len(tasks) < min_failures:
            continue
        skill_name = _domain_to_skill_name(domain)
        if existing_skills and skill_name in existing_skills:
            continue

        task_ids = [t["no_skill"]["task_id"] for t in tasks]
        instructions = []
        for tid in task_ids[:5]:
            task_dir = tasks_dir / tid
            if task_dir.exists():
                instructions.append(_read_instruction(task_dir))

        clusters.append(FailureCluster(
            domain=domain,
            failure_mode="LOW_BASELINE_SCORE",
            task_ids=task_ids,
            instructions=instructions,
            suggested_skill_name=skill_name,
            description=_auto_description(skill_name, domain),
        ))

    return clusters


# ---------------------------------------------------------------------------
# LLM draft
# ---------------------------------------------------------------------------

def draft_skill_body(cluster: FailureCluster, client) -> str:
    title = " ".join(p.capitalize() for p in cluster.suggested_skill_name.split("-"))
    instructions_block = "\n".join(
        f"{i+1}. {instr[:120]}" for i, instr in enumerate(cluster.instructions)
    )
    prompt = PROPOSE_PROMPT.format(
        n=cluster.n_failures,
        domain=cluster.domain,
        skill_name=cluster.suggested_skill_name,
        title=title,
        instructions=instructions_block,
        failure_mode=cluster.failure_mode,
    )
    msg = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.choices[0].message.content.strip()


def build_frontmatter(skill_name: str, description: str) -> str:
    return (
        "---\n"
        f"name: {skill_name}\n"
        f"description: {description}\n"
        "license: Apache-2.0\n"
        "metadata:\n"
        "  author: travel-platform\n"
        '  version: "0.1.0"\n'
        "---\n"
    )


# ---------------------------------------------------------------------------
# GitHub PR
# ---------------------------------------------------------------------------

def open_skill_pr(
    repo: str,
    skill_name: str,
    skill_content: str,
    token: str,
    title: str,
    body: str,
) -> str:
    """Create a branch, commit the skill file, open a PR. Returns PR URL."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"https://api.github.com/repos/{repo}"

    with httpx.Client(headers=headers, timeout=30) as gh:
        # Get default branch SHA
        repo_info = gh.get(base).raise_for_status().json()
        default_branch = repo_info["default_branch"]
        ref_data = gh.get(f"{base}/git/ref/heads/{default_branch}").raise_for_status().json()
        sha = ref_data["object"]["sha"]

        # Create proposal branch
        branch = f"proposal/{skill_name}"
        try:
            gh.post(f"{base}/git/refs", json={
                "ref": f"refs/heads/{branch}",
                "sha": sha,
            }).raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 422:   # 422 = branch already exists
                raise

        # Upsert the skill file
        file_path = f"skills/{skill_name}/SKILL.md"
        encoded = base64.b64encode(skill_content.encode()).decode()
        payload: dict = {
            "message": f"proposal: auto-generated {skill_name} skill",
            "content": encoded,
            "branch": branch,
        }
        # Check if file already exists (need its SHA for update)
        existing = gh.get(f"{base}/contents/{file_path}", params={"ref": branch})
        if existing.status_code == 200:
            payload["sha"] = existing.json()["sha"]
        gh.put(f"{base}/contents/{file_path}", json=payload).raise_for_status()

        # Open PR
        pr = gh.post(f"{base}/pulls", json={
            "title": title,
            "body": body,
            "head": branch,
            "base": default_branch,
        })
        if pr.status_code == 422:
            # PR already open — find it
            prs = gh.get(f"{base}/pulls", params={"head": f"{repo.split('/')[0]}:{branch}"}).json()
            return prs[0]["html_url"] if prs else branch
        pr.raise_for_status()
        return pr.json()["html_url"]


def propose_skill_pr(
    cluster: FailureCluster,
    github_token: str,
    repo: str,
    client,
) -> str:
    """Draft a new skill from a failure cluster and open a PR. Returns PR URL."""
    print(f"  Drafting body for {cluster.suggested_skill_name} ({cluster.n_failures} failures)…")
    body_md = draft_skill_body(cluster, client)
    frontmatter = build_frontmatter(cluster.suggested_skill_name, cluster.description)
    skill_content = f"{frontmatter}\n{body_md}\n"

    pr_body = (
        f"## Auto-proposed skill: `{cluster.suggested_skill_name}`\n\n"
        f"**Source:** {cluster.n_failures} failed eval tasks in domain `{cluster.domain}` "
        f"with failure mode `{cluster.failure_mode}`.\n\n"
        "**Failed tasks:**\n"
        + "".join(f"- `{tid}`\n" for tid in cluster.task_ids[:10])
        + "\n**Representative instructions:**\n"
        + "".join(f"- {instr[:100]}\n" for instr in cluster.instructions[:3])
        + "\n---\n"
        "⚠️ **Human review required.** Edit the SKILL.md body before merging.\n"
        "The CI eval gate will run automatically when this PR is opened.\n"
        "Auto-merge is never performed — a human must approve.\n"
    )

    url = open_skill_pr(
        repo=repo,
        skill_name=cluster.suggested_skill_name,
        skill_content=skill_content,
        token=github_token,
        title=f"proposal: auto-generated {cluster.suggested_skill_name} skill",
        body=pr_body,
    )
    return url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_task_domain(task_dir: Path) -> str | None:
    toml_path = task_dir / "task.toml"
    if not toml_path.exists():
        return None
    m = re.search(r'^domain\s*=\s*"([^"]+)"', toml_path.read_text(), re.MULTILINE)
    return m.group(1) if m else None


def _read_instruction(task_dir: Path) -> str:
    p = task_dir / "instruction.md"
    return p.read_text().strip()[:150] if p.exists() else ""


def _domain_to_skill_name(domain: str) -> str:
    if domain in _DOMAIN_TO_SKILL_NAME:
        return _DOMAIN_TO_SKILL_NAME[domain]
    return domain.replace("_", "-")


def _auto_description(skill_name: str, domain: str) -> str:
    title = " ".join(p.lower() for p in skill_name.split("-"))
    return (
        f"Handle {title} tasks. Auto-proposed from eval failure cluster "
        f"in domain '{domain}'. Review and edit before merging."
    )


def _load_existing_skills(skills_dir: Path) -> set[str]:
    if not skills_dir.exists():
        return set()
    return {d.name for d in skills_dir.iterdir() if d.is_dir()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Propose new skills from eval failure clusters."
    )
    parser.add_argument("--db", default="trajectory.db", help="Path to trajectory.db")
    parser.add_argument("--ab-results", default="ab_results.json")
    parser.add_argument("--tasks-dir", default="tasks")
    parser.add_argument("--skills-dir", default="../travel-agent-skills/skills",
                        help="Path to travel-agent-skills/skills to check existing skills")
    parser.add_argument("--threshold", type=int, default=5,
                        help="Minimum failures in a cluster to trigger a proposal")
    parser.add_argument("--domain", default=None, help="Only propose for this domain")
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--repo", default="Tabhi-Commons/travel-agent-skills")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print proposals without opening PRs")
    args = parser.parse_args()

    tasks_dir = Path(args.tasks_dir)
    existing = _load_existing_skills(Path(args.skills_dir))

    # Collect clusters from both sources
    clusters = load_failure_clusters(
        db_path=Path(args.db),
        tasks_dir=tasks_dir,
        min_failures=args.threshold,
        existing_skills=existing,
    )
    if not clusters:
        clusters = load_clusters_from_ab_results(
            ab_results_path=Path(args.ab_results),
            tasks_dir=tasks_dir,
            min_failures=max(args.threshold - 2, 1),
            existing_skills=existing,
        )

    if args.domain:
        clusters = [c for c in clusters if c.domain == args.domain]

    if not clusters:
        print("No qualifying failure clusters found.")
        return

    print(f"\nFound {len(clusters)} cluster(s) qualifying for skill proposals:\n")
    for c in clusters:
        print(f"  domain={c.domain}  skill={c.suggested_skill_name}  failures={c.n_failures}  mode={c.failure_mode}")

    if args.dry_run:
        import openai as _openai
        client = _openai.OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            timeout=120.0,
            max_retries=3,
        )
        for c in clusters:
            print(f"\n{'─'*60}")
            print(f"PROPOSAL: {c.suggested_skill_name}")
            print(f"{'─'*60}")
            body = draft_skill_body(c, client)
            fm = build_frontmatter(c.suggested_skill_name, c.description)
            print(fm + "\n" + body)
        return

    if not args.github_token:
        print("ERROR: --github-token or GITHUB_TOKEN env var required for PR creation.")
        return

    import openai as _openai
    client = _openai.OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=120.0,
        max_retries=3,
    )
    for c in clusters:
        url = propose_skill_pr(c, args.github_token, args.repo, client)
        print(f"  PR opened: {url}")


if __name__ == "__main__":
    main()
