import { langsmithProject } from "@/lib/data";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json({
    langsmith_project: langsmithProject(),
    langsmith_project_url: "https://smith.langchain.com",
  });
}
