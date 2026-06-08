import { allResults } from "@/lib/data";

export const dynamic = "force-dynamic";

export async function GET() {
  const leaderboard = allResults()
    .map((r) => ({
      skill: r.skill_name,
      weighted_delta: r.weighted_delta,
      regression_rate: r.regression_rate,
      n_tasks: (r.tasks ?? []).length,
      status: r.verdict ?? "",
      owners: [] as string[],
    }))
    .sort((a, b) => b.weighted_delta - a.weighted_delta);
  return Response.json({ leaderboard });
}
