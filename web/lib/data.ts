// web/lib/data.ts
// Shared server-side helpers for the dashboard API. Reads the playground repo
// that sits one level above web/ (results/, eval/optimizer_output/) plus the
// sibling travel-agent-skills repo. Pure Node — used only by route handlers.
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

function findRepoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 6; i++) {
    if (fs.existsSync(path.join(dir, "agent", "harness_config.yaml"))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  // next dev runs from web/, so the repo is the parent.
  return path.resolve(process.cwd(), "..");
}

export const REPO_ROOT = findRepoRoot();
export const SKILLS_ROOT = path.resolve(REPO_ROOT, "..", "travel-agent-skills", "skills");
export const RESULTS_DIR = path.join(REPO_ROOT, "results");
export const OPT_DIR = path.join(REPO_ROOT, "eval", "optimizer_output");
export const VENV_PYTHON = path.join(REPO_ROOT, ".venv", "bin", "python");

export type Frontmatter = {
  name?: string;
  description?: string;
  version?: string;
  author?: string;
  status?: string;
  tags?: string[];
};

export function parseSkill(dir: string): { content: string; fm: Frontmatter } | null {
  const p = path.join(dir, "SKILL.md");
  if (!fs.existsSync(p)) return null;
  const content = fs.readFileSync(p, "utf8");
  const fm: Frontmatter = {};
  const m = content.match(/^---\n([\s\S]*?)\n---/);
  if (m) {
    const block = m[1];
    const get = (re: RegExp): string | undefined => {
      const mm = block.match(re);
      return mm ? mm[1].trim().replace(/^["']|["']$/g, "") : undefined;
    };
    fm.name = get(/^name:\s*(.+)$/m);
    fm.description = get(/^description:\s*(.+)$/m);
    fm.version = get(/^\s+version:\s*(.+)$/m);
    fm.author = get(/^\s+author:\s*(.+)$/m);
    fm.status = get(/^\s+status:\s*(.+)$/m);
  }
  return { content, fm };
}

export type AbTask = { task_id: string; delta: number; task_weight: number };
export type AbResult = {
  skill_name: string;
  weighted_delta: number;
  regression_rate: number;
  verdict: string;
  tasks?: AbTask[];
};

function readAbFile(file: string): AbResult | null {
  try {
    const d = JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, file), "utf8"));
    // Skip non-skill result files (e.g. orchestrator comparisons have no skill_name).
    if (d && typeof d === "object" && typeof d.skill_name === "string") return d as AbResult;
  } catch {
    /* malformed file — ignore */
  }
  return null;
}

export function allResults(): AbResult[] {
  if (!fs.existsSync(RESULTS_DIR)) return [];
  const out: AbResult[] = [];
  for (const f of fs.readdirSync(RESULTS_DIR)) {
    if (!f.endsWith("_ab_results.json")) continue;
    const r = readAbFile(f);
    if (r) out.push(r);
  }
  return out;
}

export function resultForSkill(skill: string): AbResult | null {
  return allResults().find((r) => r.skill_name === skill) ?? null;
}

export function listSkillDirs(): string[] {
  if (!fs.existsSync(SKILLS_ROOT)) return [];
  return fs
    .readdirSync(SKILLS_ROOT)
    .filter((n) => fs.existsSync(path.join(SKILLS_ROOT, n, "SKILL.md")))
    .sort();
}

export type Commit = { sha: string; message: string; date: string; author: string };

export function skillHistory(name: string): Commit[] {
  try {
    const out = execFileSync(
      "git",
      [
        "-C", SKILLS_ROOT, "log", "-n", "10",
        "--format=%h%x1f%s%x1f%ad%x1f%an", "--date=short",
        "--", path.join(name, "SKILL.md"),
      ],
      { encoding: "utf8" }
    );
    return out
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((line) => {
        const [sha, message, date, author] = line.split("\x1f");
        return { sha, message, date, author };
      });
  } catch {
    return [];
  }
}

export type OptimizerRun = {
  run: string;
  target: string;
  improved: boolean;
  baseline_test_mixed: number | null;
  best_test_mixed: number | null;
  baseline_selection_score: number | null;
  best_selection_score: number | null;
  proposed_file: string | null;
  crashed: boolean;
  dir: string;
};

export function listOptimizerRuns(): OptimizerRun[] {
  if (!fs.existsSync(OPT_DIR)) return [];
  const runs: OptimizerRun[] = [];
  for (const name of fs.readdirSync(OPT_DIR).sort().reverse()) {
    const dir = path.join(OPT_DIR, name);
    let isDir = false;
    try {
      isDir = fs.statSync(dir).isDirectory();
    } catch {
      continue;
    }
    const rp = path.join(dir, "optimization_report.json");
    if (!isDir || !fs.existsSync(rp)) continue;
    try {
      const r = JSON.parse(fs.readFileSync(rp, "utf8"));
      runs.push({
        run: r.run ?? name,
        target: r.target ?? "",
        improved: !!r.improved,
        baseline_test_mixed: r.baseline_test_mixed ?? null,
        best_test_mixed: r.best_test_mixed ?? null,
        baseline_selection_score: r.baseline_selection_score ?? null,
        best_selection_score: r.best_selection_score ?? null,
        proposed_file: r.proposed_file ?? null,
        crashed: !!r.crashed,
        dir: name,
      });
    } catch {
      /* skip unreadable report */
    }
  }
  return runs;
}

export const EVAL_MODELS = [
  "google/gemini-2.5-flash",
  "google/gemini-2.5-pro",
  "anthropic/claude-haiku-4-5",
  "anthropic/claude-sonnet-4-6",
  "gpt-4o",
  "gpt-4o-mini",
];

export function langsmithProject(): string {
  let project = process.env.LANGCHAIN_PROJECT || process.env.LANGSMITH_PROJECT || "";
  if (!project) {
    try {
      const env = fs.readFileSync(path.join(REPO_ROOT, ".env"), "utf8");
      const m = env.match(/^(?:LANGCHAIN_PROJECT|LANGSMITH_PROJECT)\s*=\s*(.+)$/m);
      if (m) project = m[1].trim().replace(/^["']|["']$/g, "");
    } catch {
      /* no .env or unreadable */
    }
  }
  return project || "skill-testing-playground";
}
