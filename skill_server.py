"""FastAPI backend for the skill eval platform."""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys
from collections import defaultdict
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from eval.skill_loader import load_skill
from eval.leaderboard import collect_results, summarize_skill
from eval.trajectory import init_db, get_runs

SKILLS_REPO = pathlib.Path(
    os.environ.get("SKILLS_REPO", "../travel-agent-skills")
).resolve()
REGISTRY_PATH = SKILLS_REPO / "registry.yaml"
SKILLS_DIR = SKILLS_REPO / "skills"
RESULTS_DIR = pathlib.Path("results")

app = FastAPI(title="Skill Eval Platform", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    raw = yaml.safe_load(REGISTRY_PATH.read_text()) or {}
    return raw.get("skills", {})


def _last_eval(skill_name: str) -> Optional[dict]:
    path = RESULTS_DIR / f"{skill_name}_ab_results.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
        if isinstance(raw, dict):
            return raw  # new format already has weighted_delta, tasks, etc.
        if not raw:
            return None
        summary = summarize_skill(skill_name, raw)
        summary["tasks"] = raw
        return summary
    except Exception:
        return None


def _git_log(skill_name: str) -> list[dict]:
    skill_path = SKILLS_DIR / skill_name
    if not skill_path.exists():
        return []
    try:
        out = subprocess.check_output(
            [
                "git", "log", "--follow", "--pretty=format:%H|%s|%ad|%an",
                "--date=short", f"skills/{skill_name}",
            ],
            cwd=str(SKILLS_REPO),
            text=True,
        )
        commits = []
        for line in out.strip().splitlines():
            if "|" in line:
                sha, msg, date, author = line.split("|", 3)
                commits.append({"sha": sha[:8], "message": msg, "date": date, "author": author})
        return commits
    except subprocess.CalledProcessError:
        return []


# ---------------------------------------------------------------------------
# Skill endpoints
# ---------------------------------------------------------------------------

class SkillUpdate(BaseModel):
    content: str


@app.get("/api/skills")
def list_skills():
    registry = _registry()
    skills = []
    for name, meta in registry.items():
        eval_data = _last_eval(name)
        entry = {
            "name": name,
            "version": meta.get("version", "0.1.0"),
            "status": meta.get("status", "draft"),
            "owners": meta.get("owners", []),
            "tags": meta.get("tags", []),
            "weighted_delta": None,
            "regression_rate": None,
            "verdict": None,
            "last_eval": None,
        }
        if eval_data:
            entry["weighted_delta"] = eval_data.get("weighted_delta")
            entry["regression_rate"] = eval_data.get("regression_rate")
            entry["verdict"] = eval_data.get("verdict")
            entry["n_tasks"] = eval_data.get("n_tasks")
        skills.append(entry)
    return {"skills": skills}


@app.get("/api/skills/{name}")
def get_skill(name: str):
    skill_path = SKILLS_DIR / name
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    skill_file = skill_path / "SKILL.md"
    content = skill_file.read_text() if skill_file.exists() else ""
    loaded = load_skill(skill_path)

    registry = _registry()
    meta = registry.get(name, {})
    eval_data = _last_eval(name)

    return {
        "name": name,
        "content": content,
        "description": loaded.description if loaded else "",
        "body": loaded.body if loaded else content,
        "version": meta.get("version", "0.1.0"),
        "status": meta.get("status", "draft"),
        "owners": meta.get("owners", []),
        "tags": meta.get("tags", []),
        "last_eval": eval_data,
        "history": _git_log(name),
    }


@app.post("/api/skills/{name}")
def update_skill(name: str, body: SkillUpdate):
    skill_path = SKILLS_DIR / name
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    skill_file = skill_path / "SKILL.md"
    skill_file.write_text(body.content)
    return {"ok": True}


@app.get("/api/skills/{name}/history")
def skill_history(name: str):
    return {"commits": _git_log(name)}


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@app.get("/api/leaderboard")
def leaderboard():
    registry = _registry()
    rows = []
    for path in sorted(RESULTS_DIR.glob("*_ab_results.json")):
        try:
            raw = json.loads(path.read_text())
            # new format: dict with summary + tasks list
            # old format: plain list of per-task results
            if isinstance(raw, dict):
                tasks = raw.get("tasks", [])
                skill_name = raw.get("skill_name", path.stem.replace("_ab_results", ""))
                # use pre-computed summary if available
                rows.append({
                    "skill": skill_name,
                    "weighted_delta": round(raw.get("weighted_delta", 0), 3),
                    "regression_rate": round(raw.get("regression_rate", 0), 2),
                    "n_tasks": len(tasks),
                    "verdict": raw.get("verdict"),
                    "status": registry.get(skill_name, {}).get("status", "draft"),
                    "owners": registry.get(skill_name, {}).get("owners", []),
                })
            else:
                tasks = raw
                if not tasks:
                    continue
                skill_name = tasks[0].get("skill_name", path.stem.replace("_ab_results", ""))
                summary = summarize_skill(skill_name, tasks)
                meta = registry.get(skill_name, {})
                rows.append({
                    **summary,
                    "status": meta.get("status", "draft"),
                    "owners": meta.get("owners", []),
                })
        except Exception:
            continue
    rows.sort(key=lambda x: x.get("weighted_delta", 0), reverse=True)
    return {"leaderboard": rows}


# ---------------------------------------------------------------------------
# Eval runner — SSE streaming
# ---------------------------------------------------------------------------

SUPPORTED_MODELS = [
    "google/gemini-2.5-flash",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1-mini",
    "google/gemini-2.5-pro",
    "anthropic/claude-haiku-4-5",
]

class EvalRequest(BaseModel):
    skill_name: str
    trials: int = 3
    model: str = "google/gemini-2.5-flash"
    output: Optional[str] = None


@app.get("/api/models")
def list_models():
    return {"models": SUPPORTED_MODELS}


async def _stream_eval(skill_name: str, trials: int, output: str, model: str = "google/gemini-2.5-flash"):
    skill_path = SKILLS_DIR / skill_name
    if not skill_path.exists():
        yield f"data: ERROR: skill '{skill_name}' not found\n\n"
        return

    cmd = [
        sys.executable, "-m", "eval.ab_compare",
        "--skill-path", str(skill_path),
        "--trials", str(trials),
        "--model", model,
    ]
    if output:
        cmd += ["--output", output]

    yield f"data: Starting eval: {skill_name}  model={model}  trials={trials}\n\n"

    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        cwd=str(pathlib.Path(__file__).parent),
    )

    async for line in proc.stdout:
        text = line.decode(errors="replace").rstrip()
        if text:
            yield f"data: {text}\n\n"

    await proc.wait()
    code = proc.returncode
    verdict = "PASS" if code == 0 else "BLOCK"
    yield f"data: __DONE__ {verdict}\n\n"


@app.post("/api/eval/run")
async def run_eval(req: EvalRequest):
    output = req.output or f"results/{req.skill_name}_ab_results.json"
    pathlib.Path(output).parent.mkdir(parents=True, exist_ok=True)
    return StreamingResponse(
        _stream_eval(req.skill_name, req.trials, output, req.model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Trajectories
# ---------------------------------------------------------------------------

@app.get("/api/trajectories")
def trajectories(skill: Optional[str] = None, limit: int = 50):
    rows = get_runs(skill_name=skill, limit=limit)
    return {
        "trajectories": [
            {
                "run_id": r.run_id, "task_id": r.task_id, "skill_name": r.skill_name,
                "condition": r.condition, "score": r.score, "passed": r.passed,
                "failure_mode": r.failure_mode, "langsmith_url": r.langsmith_url,
                "steps": len(r.steps),
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# Skill detection
# ---------------------------------------------------------------------------

class DetectRequest(BaseModel):
    message: str


@app.post("/api/skills/detect")
def detect_skill(req: DetectRequest):
    try:
        from eval.skill_router import SkillRouter
        skill_paths = [p for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists()]
        router = SkillRouter.from_skill_paths(skill_paths)
        match = router.route(req.message, threshold=0.30)
        if match:
            return {"skill": match.skill_name, "score": match.score, "matched": True}
        return {"skill": None, "score": 0.0, "matched": False}
    except Exception as e:
        return {"skill": None, "score": 0.0, "matched": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Observability — optimizer runs
# ---------------------------------------------------------------------------

OPTIMIZER_OUTPUT_DIR = pathlib.Path("eval/optimizer_output")


def _parse_optimizer_run(run_dir: pathlib.Path) -> Optional[dict]:
    """Return a summary dict for one optimizer run dir, or None if missing report."""
    report_path = run_dir / "optimization_report.json"
    if not report_path.exists():
        return None
    try:
        report = json.loads(report_path.read_text())
    except Exception:
        return None
    run_tag = run_dir.name
    return {
        "run": report.get("run", run_tag),
        "target": report.get("target", ""),
        "improved": bool(report.get("improved", False)),
        "baseline_test_mixed": report.get("baseline_test_mixed"),
        "best_test_mixed": report.get("best_test_mixed"),
        "baseline_selection_score": report.get("baseline_selection_score"),
        "best_selection_score": report.get("best_selection_score"),
        "proposed_file": report.get("proposed_file"),
        "crashed": bool(report.get("crashed", False)),
        "dir": str(run_dir),
    }


@app.get("/api/optimizer-runs")
def list_optimizer_runs():
    """Scan eval/optimizer_output and return all runs sorted newest-first."""
    if not OPTIMIZER_OUTPUT_DIR.exists():
        return {"runs": []}
    runs = []
    for run_dir in sorted(OPTIMIZER_OUTPUT_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        entry = _parse_optimizer_run(run_dir)
        if entry is not None:
            runs.append(entry)
    return {"runs": runs}


@app.get("/api/optimizer-runs/{run_tag:path}")
def get_optimizer_run(run_tag: str):
    """Return full report + before/after artifact texts for one run."""
    run_dir = OPTIMIZER_OUTPUT_DIR / run_tag
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_tag}' not found")
    report_path = run_dir / "optimization_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"No report for '{run_tag}'")
    try:
        report = json.loads(report_path.read_text())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    initial_text = None
    initial_path = run_dir / "initial_artifact.md"
    if initial_path.exists():
        initial_text = initial_path.read_text()

    best_text = None
    best_path = run_dir / "best_skill.md"
    if best_path.exists():
        best_text = best_path.read_text()

    skill_versions = sorted(
        [p.name for p in (run_dir / "skills").iterdir() if p.suffix == ".md"]
    ) if (run_dir / "skills").exists() else []

    return {
        "report": report,
        "initial_artifact": initial_text,
        "best_skill": best_text,
        "skill_versions": skill_versions,
    }


@app.get("/api/observability/links")
def observability_links():
    """Return external observability deep-links (LangSmith, etc.)."""
    project = os.environ.get("LANGSMITH_PROJECT", "skill-testing-playground")
    return {
        "langsmith_project": project,
        "langsmith_project_url": "https://smith.langchain.com",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("skill_server:app", host="0.0.0.0", port=8000, reload=True)
