import { EVAL_MODELS } from "@/lib/data";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json({ models: EVAL_MODELS });
}
