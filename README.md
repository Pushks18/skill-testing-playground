# skill-testing-playground

Eval and optimization platform for the travel-agent skill system. It measures
whether each skill actually helps the agent (A/B evals over a 466-task bank),
proposes improvements when skills fail (propose-only optimizer, human-reviewed),
and gates every skill change in CI before a human merges.

**Companion repo:** [`travel-agent-skills`](../travel-agent-skills) — the skills
themselves (SKILL.md files, registry, packaging CLI). The two repos must be
cloned side by side; this platform reads skills from `../travel-agent-skills/skills`.

**Full architecture with flow diagrams:** [docs/architecture.html](docs/architecture.html)
(open in a browser; diagrams render via Mermaid CDN).

---

## How it works in one paragraph

Each task in `tasks/` declares what a correct agent must do (required tool calls
+ params, or LLM-judge criteria) and how much it matters (weight). The eval runs
every task twice — agent **without** the skill vs **with** the skill injected —
against a deterministic mock travel API. The per-task score delta, weighted and
aggregated, goes through a tiered gate (PASS / SOFT_BLOCK / BLOCK). Failures are
clustered and fed to an optimizer that proposes skill-text or harness edits;
a human reviews every proposal; the gate re-judges the result. CI runs the same
gate on every skill PR.

---

## Setup

```bash
# 1. Clone both repos as siblings
git clone <this-repo>            skill-testing-playground
git clone <travel-agent-skills>  travel-agent-skills

# 2. Python env (3.11)
cd skill-testing-playground
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Secrets — create .env at the repo root
OPENAI_API_KEY=sk-...            # everything runs on this one key
LANGFUSE_PUBLIC_KEY=pk-lf-...    # optional: per-run tracing
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGCHAIN_TRACING_V2=false

# 4. Start the mock travel API (required for evals)
.venv/bin/python eval/mock_mcp/server.py &        # port 8000, /health to check

# 5. Sanity check — no API keys needed for tests
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_skillopt_spike.py
```

## Everyday commands

| What | Command |
|---|---|
| A/B-eval one skill | `.venv/bin/python eval/ab_compare.py --skill-path ../travel-agent-skills/skills/<skill> --trials 3` |
| Launch the ops UI | `.venv/bin/streamlit run ui/app.py` → http://localhost:8501 |
| Expand a task domain to N tasks | `.venv/bin/python scripts/expand_bank.py --domains <domain> --target 50` |
| Run the optimizer on a failure classification | `scripts/run_optimizer_scoped.sh` (domain-scoped, cost-capped) |
| Classify failures from results | `.venv/bin/python eval/classify_failures.py …` |

## The ops UI (Streamlit)

`streamlit run ui/app.py`, then use the sidebar pages:

- **Leaderboard** — per-skill deltas and verdicts from `results/`
- **Skill Manager** — browse / edit / eval skills
- **Trajectories** — per-run tool-call sequences from `trajectory.db`
- **Task Bank** — bank coverage, task browser, **add a new task through the
  real QC gates** (validate → dedupe → optional live calibration → promote),
  and the improvement-proposals queue

## Adding a task (human flow)

1. Open **Task Bank → Add a Task** in the UI.
2. Pick the domain (this binds the task to its owning skill), write the user
   instruction, choose the verifier, declare required tools/params or judge
   criteria, set the weight (3.0 = business-critical, trips the tier-1 gate alone).
3. **Run gates** — structural validation + embedding dedupe against the whole
   bank. Optionally run the one-trial live calibration.
4. **Promote** (enabled only when gates pass), then commit the new `tasks/<id>/`.

For a **brand-new skill**: add one line to `DOMAIN_TARGETS`/`DOMAIN_SKILL` in
`eval/taskgen.py` first. CI enforces coverage — `tests/test_skill_task_coverage.py`
fails the build until every evaluable skill has ≥ 10 tasks.

## Improvement proposals

- `proposals/` — the curated, human-readable queue: one evidence-backed file per
  item, naming the layer that needs the update (skill text / harness / eval
  infra / model weights). Index table in `proposals/README.md`.
- `eval/optimizer_output/<run>/` — the optimizer's raw machine proposals
  (`*_proposed.md|yaml` + `optimization_report.json` with before/after scores).
- Nothing is auto-applied: human reviews the diff, applies or rejects, the
  full A/B gate re-judges.

## CI / CD

| Workflow | Trigger | What it does |
|---|---|---|
| `tests.yml` | every push / PR | 284-test suite on a clean runner, no API keys needed |
| `eval_skill.yml` (here) and `eval.yml` (skills repo) | PR touching `skills/**` | validate + security-scan the skill, boot the mock API, run a 5-trial A/B (~$0.03), post the gate verdict as a PR comment |

**Repo secrets** (Settings → Secrets → Actions): `OPENAI_API_KEY` (required for
eval gates), `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST`
(optional tracing), `EVAL_PLATFORM_TOKEN` in the skills repo only if this repo
is private.

## Tracing (Langfuse)

With the `LANGFUSE_*` env vars set, every agent run records a full trace
(prompts, tool calls, latencies). Trace URLs flow into `ab_results.json` →
`regression_traces`, so every regressed task in a CI verdict comment links
straight to its trace. Without the keys, tracing is a complete no-op — tests
and CI run key-free.

## Repository layout

```
agent/            LangGraph travel agent + harness_config.yaml (optimizable)
eval/             evals, verifiers, gate, taskgen, optimizer, mock API, tracing
tasks/            the task bank (466 tasks, 9 domains) — ground truth
tasks_drafts/     taskgen staging + QC evidence archive
proposals/        curated improvement queue (human-readable)
results/          per-skill A/B results (JSON)
scripts/          expand_bank.py, run_optimizer_scoped.sh
ui/               Streamlit ops app (leaderboard, skills, trajectories, task bank)
docs/             architecture.html (flow diagrams) + design notes
tests/            284 tests — all heavy I/O stubbed, runs key-free
```
