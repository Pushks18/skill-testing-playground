import path from "node:path";
import { spawn } from "node:child_process";
import { REPO_ROOT, SKILLS_ROOT, VENV_PYTHON, listSkillDirs } from "@/lib/data";

export const dynamic = "force-dynamic";

// Streams an A/B eval (eval.ab_compare) as Server-Sent Events. Each stdout line
// becomes `data: <line>`; the gate verdict line is parsed and re-emitted as a
// terminal `data: __DONE__ <VERDICT>` the frontend keys off. This SPENDS money
// (real model calls) — it is gated only by being an explicit user action.
export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const skill_name: string = body?.skill_name ?? "";
  const trials: number = Number(body?.trials) || 3;
  const model: string = body?.model ?? "google/gemini-2.5-flash";

  if (!skill_name || !listSkillDirs().includes(skill_name)) {
    return Response.json({ error: "unknown skill_name" }, { status: 400 });
  }

  const skillPath = path.join(SKILLS_ROOT, skill_name);
  const args = [
    "-m", "eval.ab_compare",
    "--skill-path", skillPath,
    "--trials", String(trials),
    "--model", String(model),
  ];

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder();
      const send = (s: string) => controller.enqueue(enc.encode(`data: ${s}\n\n`));

      const child = spawn(VENV_PYTHON, args, {
        cwd: REPO_ROOT,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: "1",
          // Silence LangSmith tracing noise so the stream is readable.
          LANGCHAIN_TRACING_V2: "false",
          LANGSMITH_TRACING: "false",
        },
      });

      let verdict = "WARN";
      let buf = "";

      const handle = (data: Buffer) => {
        buf += data.toString();
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          if (/multipart|langsmith|trace=/i.test(line)) continue; // drop tracing spam
          const m = line.match(/GATE VERDICT:\s*([A-Z_ ]+)/);
          if (m) verdict = m[1].includes("BLOCK") ? "BLOCK" : m[1].trim().split(/\s+/)[0];
          send(line.trimEnd());
        }
      };

      child.stdout.on("data", handle);
      child.stderr.on("data", handle);

      child.on("error", (e) => {
        send(`error launching eval: ${e.message}`);
        send(`__DONE__ BLOCK`);
        controller.close();
      });

      child.on("close", (code) => {
        if (buf.trim() && !/multipart|langsmith|trace=/i.test(buf)) send(buf.trim());
        if (code !== 0 && verdict === "WARN") send(`(eval process exited with code ${code})`);
        send(`__DONE__ ${verdict}`);
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
