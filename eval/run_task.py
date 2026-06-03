# eval/run_task.py
"""Run a single task through the travel agent and return an EvalResult."""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys
import time

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import langsmith
from openinference.instrumentation.langchain import LangChainInstrumentor
from opentelemetry.sdk.trace import TracerProvider

from agent.travel_agent import build_travel_agent
from eval.schemas import EvalResult
from eval.verifiers.tool_call import ToolCallVerifier
from eval.verifiers.llm_judge import LLMJudgeVerifier

try:
    LangChainInstrumentor().instrument(tracer_provider=TracerProvider())
except Exception:
    pass  # Instrumentation is best-effort; tracing via LangSmith still works


def load_task(task_path: pathlib.Path) -> dict:
    import re, json as _json
    raw = (task_path / "task.toml").read_text()
    # Fix JSON-style inline tables ({"key": val}) → valid TOML ({"key" = val})
    # tomli requires = in inline tables, not :
    def fix_inline(m):
        return m.group(0).replace(": ", " = ").replace(":", " = ")
    raw = re.sub(r'\{[^}]+\}', fix_inline, raw)
    meta = tomllib.loads(raw)
    instruction = (task_path / "instruction.md").read_text().strip()
    return {**meta["task"], "expected": meta.get("expected", {}), "instruction": instruction}


def load_skill(skill_path) -> str | None:
    if skill_path is None:
        return None
    skill_file = pathlib.Path(skill_path) / "SKILL.md"
    if skill_file.exists():
        return skill_file.read_text()
    return None


@langsmith.traceable(name="skill_eval")
def run_task(
    task_path: str,
    skill_path=None,
    condition: str = "no_skill",
    mock_mcp_url: str = "http://localhost:8000",
) -> EvalResult:
    task_dir = pathlib.Path(task_path)
    task = load_task(task_dir)
    skill_content = load_skill(skill_path)

    agent = build_travel_agent(skill_content=skill_content, mock_mcp_url=mock_mcp_url)

    start = time.time()
    result = agent.invoke({
        "messages": [{"role": "user", "content": task["instruction"]}],
        "tools_called": [],
        "response": "",
        "steps": 0,
        "tokens_used": 0,
    })
    latency_ms = int((time.time() - start) * 1000)

    verifier_type = task.get("verifier", "tool_call_check")
    expected = task.get("expected", {})

    if verifier_type == "tool_call_check":
        verifier = ToolCallVerifier(
            required_tools=expected.get("tools", []),
            required_params=expected.get("required_params", {}),
        )
    else:
        verifier = LLMJudgeVerifier(instruction=task["instruction"])

    agent_output = {
        "response": result.get("response", ""),
        "tools_called": result.get("tools_called", []),
    }
    vresult = verifier.verify(agent_output)

    return EvalResult(
        task_id=task["id"],
        domain=task["domain"],
        skill_name=task.get("skill") if skill_path else None,
        skill_version=None,
        score=vresult.score,
        steps=result.get("steps", 0),
        tools_called=[t["name"] for t in result.get("tools_called", [])],
        tool_params={t["name"]: t.get("params", {}) for t in result.get("tools_called", [])},
        langsmith_run_id="",
        passed_verifier=vresult.passed,
        judge_reasoning=vresult.reason,
        latency_ms=latency_ms,
        tokens_used=result.get("tokens_used", 0),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--skill", default=None)
    parser.add_argument("--condition", default="no_skill")
    parser.add_argument("--mock-mcp-url", default=os.environ.get("MOCK_MCP_URL", "http://localhost:8000"))
    args = parser.parse_args()

    result = run_task(args.task, args.skill, args.condition, args.mock_mcp_url)
    print(json.dumps(result.__dict__, indent=2))
