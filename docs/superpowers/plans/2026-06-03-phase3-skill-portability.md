# Phase 3: Skill Portability — Skills as /commands in Any Agent System

**Ultimate goal:** Every skill in `travel-agent-skills` should be loadable as a `/command` in any AI agent environment — Claude Code, Cursor, VS Code extensions, custom LangGraph agents, API clients — the same way `/brainstorm`, `/code-review`, and other Claude Code skills work today.

**The insight:** A SKILL.md file is already a structured prompt document. The gap is the runtime layer: there's no standard way to discover, load, and invoke a skill from an arbitrary agent session. This phase builds that layer.

---

## What "skills as /commands" means

```
# Today (manual)
python -m eval.ab_compare --skill concrete/flight-search

# Phase 3 goal (any agent)
/flight-search find me flights from JFK to LAX next week
/book-itinerary plan a 3-day trip to Chicago
/fare-rules what's the cancellation policy on FL555
```

The same skill works:
- As a Claude Code `/command` (via `.claude/skills/` install)
- As a LangGraph node (loaded at agent build time)
- As an API endpoint (skill server)
- As an exported package (npm/pip installable)
- As a shareable URL (agentskills.io registry)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Skill Registry (agentskills.io)               │
│              browse / publish / version skills                   │
└───────────────────────┬─────────────────────────────────────────┘
                        │  pull / push
          ┌─────────────┼──────────────────┐
          ▼             ▼                  ▼
┌─────────────┐  ┌─────────────┐  ┌──────────────────┐
│ Claude Code │  │  Skill API  │  │  LangGraph Agent  │
│ /commands   │  │  server     │  │  (existing)        │
│ .claude/    │  │  (FastAPI)  │  │                    │
│ skills/     │  │  POST /invoke│  │                   │
└─────────────┘  └─────────────┘  └──────────────────┘
        ▲                ▲                  ▲
        └────────────────┴──────────────────┘
                         │
              eval/skill_loader.py
              (common loading layer)
```

---

## Module 1: Skill Loader (common layer)

`eval/skill_loader.py` — the shared runtime that every integration uses.

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml, re

@dataclass
class LoadedSkill:
    name: str
    layer: str                    # atomic / concrete / abstract
    content: str                  # full SKILL.md text
    trigger_phrases: list[str]    # extracted from "When to Use"
    workflow_steps: list[str]     # extracted from "## Workflow"
    tools_required: list[str]     # extracted from tool references
    reuse_refs: list[str]         # [reuse skill: X] references
    system_prompt: str            # ready-to-inject string

def load_skill(path: Path) -> LoadedSkill:
    """Parse a SKILL.md into a structured LoadedSkill."""

def load_skill_by_name(name: str, skills_dir: Path = Path("skills")) -> Optional[LoadedSkill]:
    """Find and load a skill by name across all layers."""

def skill_to_system_prompt(skill: LoadedSkill, base_prompt: str) -> str:
    """Inject skill into an agent system prompt."""

def detect_relevant_skill(user_message: str, skills: list[LoadedSkill]) -> Optional[LoadedSkill]:
    """
    Simple keyword-match router: check user message against
    each skill's trigger_phrases. Returns best match or None.
    No LLM required for basic routing.
    """
```

---

## Module 2: Skill API Server

A FastAPI server that wraps the LangGraph agent, exposing skills as REST endpoints. Any system that can POST JSON can invoke a skill.

```
POST /skills                    → list all available skills
GET  /skills/{name}             → get skill metadata
POST /skills/{name}/invoke      → run skill against a task
GET  /skills/{name}/eval        → latest eval results for skill
POST /skills/detect             → detect which skill matches a message
```

```python
# skill_server.py
from fastapi import FastAPI
from eval.skill_loader import load_skill_by_name, detect_relevant_skill
from agent.travel_agent import build_travel_agent

app = FastAPI(title="Travel Agent Skill Server")

@app.post("/skills/{name}/invoke")
async def invoke_skill(name: str, body: InvokeRequest):
    skill = load_skill_by_name(name)
    agent = build_travel_agent(skill_content=skill.system_prompt)
    result = agent.invoke({"messages": [{"role": "user", "content": body.message}], ...})
    return {"response": result["response"], "tools_called": result["tools_called"]}

@app.post("/skills/detect")  
async def detect_skill(body: DetectRequest):
    skills = load_all_skills()
    match = detect_relevant_skill(body.message, skills)
    return {"skill": match.name if match else None}
```

---

## Module 3: Claude Code /command Export

Convert any SKILL.md into a Claude Code skill installable via `.claude/skills/`. This is exactly the format used by `/brainstorm`, `/code-review`, etc.

### Skill export format

Each exported skill becomes a directory:
```
~/.claude/skills/flight-search/
├── skill.md          # the SKILL.md content (renamed)
├── metadata.json     # name, version, author, tools_required
└── hooks.json        # optional: pre/post invocation hooks
```

### Export CLI

```bash
# Export single skill to Claude Code format
python -m eval.export_skill --skill concrete/flight-search --target ~/.claude/skills/

# Export all skills
python -m eval.export_skill --all --target ~/.claude/skills/

# Export to a shareable zip
python -m eval.export_skill --all --format zip --output travel-skills-v1.0.zip
```

After export, in any Claude Code session:
```
/flight-search find flights from JFK to LAX on July 10
/hotel-search hotels in Miami from July 10-13
/fare-rules cancellation policy for FL123
```

### `eval/export_skill.py`

```python
import argparse, json, shutil
from pathlib import Path
from eval.skill_loader import load_skill, load_all_skills

def export_to_claude_code(skill, target_dir: Path):
    skill_dir = target_dir / skill.name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "skill.md").write_text(skill.content)
    (skill_dir / "metadata.json").write_text(json.dumps({
        "name": skill.name,
        "layer": skill.layer,
        "tools_required": skill.tools_required,
        "version": "1.0.0",
        "source": "travel-agent-skills",
    }, indent=2))

def export_to_zip(skills, output: Path):
    import zipfile
    with zipfile.ZipFile(output, "w") as zf:
        for skill in skills:
            zf.writestr(f"{skill.name}/skill.md", skill.content)
            zf.writestr(f"{skill.name}/metadata.json", json.dumps({...}))
```

---

## Module 4: Skill Registry (agentskills.io integration)

Publish and pull skills from the agentskills.io open registry.

```bash
# Publish a skill to registry
python -m eval.registry push --skill concrete/flight-search --version 1.2.0

# Pull a skill from registry into this project
python -m eval.registry pull --skill travel/hotel-search --version latest

# List published skills
python -m eval.registry list --org mondee
```

### `eval/registry.py`

```python
import httpx

REGISTRY_URL = "https://registry.agentskills.io/v1"

def push_skill(skill_path: Path, version: str, api_key: str):
    """Publish a SKILL.md to the registry."""

def pull_skill(org: str, name: str, version: str, target_dir: Path):
    """Download a skill from the registry."""

def list_skills(org: str) -> list[dict]:
    """List all published skills for an org."""
```

---

## Module 5: Skill Package (pip/npm installable)

For teams that want to vendor skills as a dependency rather than pulling from a registry.

```bash
pip install travel-agent-skills      # installs skills as Python package
```

```python
# Usage in any Python agent
from travel_agent_skills import load_skill, FLIGHT_SEARCH, HOTEL_SEARCH

agent = build_my_agent(skill=load_skill(FLIGHT_SEARCH))
```

The package is auto-generated from the `skills/` directory via `scripts/build_package.py`:
- Reads all SKILL.md files
- Generates `travel_agent_skills/__init__.py` with named constants
- Publishes to PyPI via GitHub Actions on version tag

---

## Build Order

### Week 3, Days 1-2: Skill Loader + API Server
The common loading layer and REST API. Everything else builds on these.

1. `eval/skill_loader.py` — parser + router
2. `skill_server.py` — FastAPI skill server  
3. Test: `curl -X POST http://localhost:9000/skills/flight-search/invoke -d '{"message": "flights JFK to LAX July 10"}'`

### Week 3, Days 3-4: Claude Code Export
Makes skills immediately usable as /commands.

4. `eval/export_skill.py` — export to `.claude/skills/` format
5. Export all 4 current skills, test as /commands in this Claude Code session
6. Add export step to CI: every merged skill PR auto-exports to a `dist/` branch

### Week 4: Registry + Package
7. `eval/registry.py` — agentskills.io push/pull
8. `scripts/build_package.py` — pip package generator
9. GitHub Actions: tag → publish to PyPI

---

## Integration with Phase 2

The trajectory observability (Phase 2) feeds directly into portability:
- When a skill is exported, its eval metrics travel with it (`metadata.json` includes `eval_score`, `regression_rate`)
- The skill server exposes `/skills/{name}/eval` so any consumer can check quality before using a skill
- The Claude Code export includes last eval date — stale skills (not eval'd in 30 days) show a warning on load

---

## Success criteria

| Milestone | Done when |
|-----------|-----------|
| Skill loader | `load_skill("flight-search")` returns structured object with trigger_phrases and system_prompt |
| Skill server | `POST /skills/flight-search/invoke` returns agent response via REST |
| Claude Code export | `/flight-search find flights JFK LAX July 10` works in this session |
| Registry push | Skill appears on agentskills.io after `python -m eval.registry push` |
| Pip package | `pip install travel-agent-skills && python -c "from travel_agent_skills import FLIGHT_SEARCH"` works |
