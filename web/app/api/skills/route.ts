import path from "node:path";
import { listSkillDirs, parseSkill, resultForSkill, SKILLS_ROOT } from "@/lib/data";

export const dynamic = "force-dynamic";

export async function GET() {
  const skills = listSkillDirs().map((name) => {
    const parsed = parseSkill(path.join(SKILLS_ROOT, name));
    const res = resultForSkill(name);
    return {
      name,
      version: parsed?.fm.version ?? "0.0.0",
      status: parsed?.fm.status ?? "active",
      owners: parsed?.fm.author ? [parsed.fm.author] : [],
      tags: parsed?.fm.tags ?? [],
      weighted_delta: res ? res.weighted_delta : null,
      verdict: res ? res.verdict : null,
    };
  });
  return Response.json({ skills });
}
