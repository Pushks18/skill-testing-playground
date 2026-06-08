import fs from "node:fs";
import path from "node:path";
import { OPT_DIR } from "@/lib/data";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ tag: string }> };

export async function GET(_req: Request, ctx: Ctx) {
  const { tag } = await ctx.params;
  // Guard against path traversal — tag must be a single directory name.
  if (tag.includes("/") || tag.includes("..")) {
    return Response.json({ error: "invalid tag" }, { status: 400 });
  }
  const dir = path.join(OPT_DIR, tag);
  if (!fs.existsSync(dir)) return Response.json({ error: "run not found" }, { status: 404 });

  const readIf = (f: string): string | null => {
    const p = path.join(dir, f);
    return fs.existsSync(p) ? fs.readFileSync(p, "utf8") : null;
  };

  let report: Record<string, unknown> = {};
  try {
    report = JSON.parse(readIf("optimization_report.json") ?? "{}");
  } catch {
    /* leave empty */
  }

  const skillsDir = path.join(dir, "skills");
  let skill_versions: string[] = [];
  if (fs.existsSync(skillsDir)) {
    skill_versions = fs.readdirSync(skillsDir).filter((f) => f.endsWith(".md")).sort();
  }

  return Response.json({
    report,
    initial_artifact: readIf("initial_artifact.md"),
    best_skill: readIf("best_skill.md"),
    skill_versions,
  });
}
