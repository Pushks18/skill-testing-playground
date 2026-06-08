import fs from "node:fs";
import path from "node:path";
import {
  parseSkill,
  resultForSkill,
  skillHistory,
  SKILLS_ROOT,
} from "@/lib/data";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ name: string }> };

export async function GET(_req: Request, ctx: Ctx) {
  const { name } = await ctx.params;
  const dir = path.join(SKILLS_ROOT, name);
  const parsed = parseSkill(dir);
  if (!parsed) return Response.json({ error: "skill not found" }, { status: 404 });

  const res = resultForSkill(name);
  const last_eval = res
    ? {
        weighted_delta: res.weighted_delta,
        regression_rate: res.regression_rate,
        n_tasks: (res.tasks ?? []).length,
        tasks: (res.tasks ?? []).map((t) => ({
          task_id: t.task_id,
          delta: t.delta,
          task_weight: t.task_weight,
        })),
      }
    : null;

  return Response.json({
    name,
    content: parsed.content,
    description: parsed.fm.description ?? "",
    version: parsed.fm.version ?? "0.0.0",
    status: parsed.fm.status ?? "active",
    owners: parsed.fm.author ? [parsed.fm.author] : [],
    tags: parsed.fm.tags ?? [],
    last_eval,
    history: skillHistory(name),
  });
}

export async function POST(request: Request, ctx: Ctx) {
  const { name } = await ctx.params;
  const p = path.join(SKILLS_ROOT, name, "SKILL.md");
  if (!fs.existsSync(p)) return Response.json({ error: "skill not found" }, { status: 404 });
  const body = await request.json();
  if (typeof body?.content !== "string") {
    return Response.json({ error: "content (string) required" }, { status: 400 });
  }
  fs.writeFileSync(p, body.content, "utf8");
  return Response.json({ ok: true });
}
