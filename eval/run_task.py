# eval/run_task.py
"""Run a single task through the travel agent and return an EvalResult."""
from __future__ import annotations
import argparse
import dataclasses
import json
import os
import pathlib
import sys
import time
import uuid

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from agent.travel_agent import build_travel_agent
from eval.schemas import EvalResult
from eval.cost import compute_cost
from eval.skill_loader import load_skill as _load_skill_structured
from eval.verifiers.tool_call import ToolCallVerifier
from eval.verifiers.llm_judge import LLMJudgeVerifier
from eval.trajectory import (
    TrajectoryRun, TrajectoryStep, save_run, classify_failure,
)

# ---------------------------------------------------------------------------
# Langfuse — optional; eval runs proceed even if keys are absent
# ---------------------------------------------------------------------------
_LANGFUSE_ENABLED = bool(
    os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
)

def _make_langfuse_handler(skill_name: str, condition: str, task_id: str, run_id: str):
    if not _LANGFUSE_ENABLED:
        return None
    try:
        from langfuse.callback import CallbackHandler
        return CallbackHandler(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            tags=[f"skill:{skill_name}", f"condition:{condition}", f"task:{task_id}"],
            session_id=f"{task_id}__{run_id}",
        )
    except Exception:
        return None


def _push_score(handler, score: float, reason: str) -> None:
    if handler is None:
        return
    try:
        handler.langfuse.score(
            trace_id=handler.get_trace_id(),
            name="verifier_score",
            value=score,
            comment=reason,
        )
    except Exception:
        pass


def _trace_url(handler) -> str | None:
    if handler is None:
        return None
    try:
        return handler.get_trace_url()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Task / skill loaders
# ---------------------------------------------------------------------------

def load_task(task_path: pathlib.Path) -> dict:
    import re
    raw = (task_path / "task.toml").read_text()
    def fix_inline(m):
        return m.group(0).replace(": ", " = ").replace(":", " = ")
    raw = re.sub(r'\{[^}]+\}', fix_inline, raw)
    meta = tomllib.loads(raw)
    instruction = (task_path / "instruction.md").read_text().strip()
    task = {**meta["task"], "expected": meta.get("expected", {}), "instruction": instruction}
    # Ensure hidden_details (if present in [expected]) is accessible via task["expected"]
    # and multi_turn is promoted from meta["task"] into top-level task dict (already merged above).
    return task


# ---------------------------------------------------------------------------
# Multi-turn user simulation
# ---------------------------------------------------------------------------

USER_SIM_SYSTEM = """You are a traveler talking to a travel-assistant AI.
Your situation (already told to the assistant): {instruction}
Additional facts you know (reveal ONLY what is asked for): {hidden_details}
The assistant just asked you something. Reply in first person, briefly (1-2
sentences), answering ONLY what was asked. Do not add new requests. If you
don't know an asked fact, say you don't know."""


def _simulate_user_reply(task: dict, agent_question: str) -> str:
    """One simulated user turn (gpt-4o-mini). Terse by design — leakage of
    unasked facts would inflate scores."""
    import openai
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model="gpt-4o-mini", max_tokens=80, temperature=0.0,
        messages=[
            {"role": "system", "content": USER_SIM_SYSTEM.format(
                instruction=task["instruction"],
                hidden_details=task.get("expected", {}).get("hidden_details", "(none)"))},
            {"role": "user", "content": agent_question},
        ],
    )
    return resp.choices[0].message.content.strip()


def _looks_like_question(response: str) -> bool:
    tail = (response or "").strip()[-300:]
    return "?" in tail


def load_skill(skill_path) -> str | None:
    if skill_path is None:
        return None
    skill = _load_skill_structured(pathlib.Path(skill_path))
    return skill.body if skill else None


# ---------------------------------------------------------------------------
# Main eval runner
# ---------------------------------------------------------------------------

def run_task(
    task_path: str,
    skill_path=None,
    condition: str = "no_skill",
    mock_mcp_url: str = "http://localhost:8000",
    model: str = None,
) -> EvalResult:
    task_dir = pathlib.Path(task_path)
    task = load_task(task_dir)
    skill_content = load_skill(skill_path)
    skill_name = pathlib.Path(skill_path).name if skill_path else "no_skill"
    expected = task.get("expected", {})
    run_id = str(uuid.uuid4())

    langfuse_handler = _make_langfuse_handler(
        skill_name=skill_name,
        condition=condition,
        task_id=task["id"],
        run_id=run_id,
    )
    callbacks = [langfuse_handler] if langfuse_handler else []

    _model = "gpt-4o-mini"
    agent = build_travel_agent(skill_content=skill_content, mock_mcp_url=mock_mcp_url)

    max_user_turns = 2 if task.get("multi_turn") else 0

    # Accumulated across all rounds
    acc_tools_called: list = []
    acc_step_timings: list = []
    acc_steps: int = 0
    acc_tokens_used: int = 0
    acc_input_tokens: int = 0
    acc_output_tokens: int = 0

    # Conversation message history — grows across rounds
    messages: list = [{"role": "user", "content": task["instruction"]}]
    n_user_turns: int = 0
    result: dict = {}

    start = time.time()
    for _round in range(max_user_turns + 1):
        result = agent.invoke(
            {
                "messages": messages,
                "tools_called": [],
                "step_timings": [],
                "response": "",
                "steps": 0,
                "tokens_used": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            },
            config={
                # LangSmith trace identity: filterable by skill / condition / task
                "run_name": f"{task['id']}__{condition}",
                "tags": [f"skill:{skill_name}", f"condition:{condition}",
                         f"domain:{task['domain']}"],
                "metadata": {"task_id": task["id"], "run_id": run_id},
                **({"callbacks": callbacks} if callbacks else {}),
            },
        )

        # Accumulate across rounds
        round_tools = result.get("tools_called", [])
        acc_tools_called.extend(round_tools)
        acc_step_timings.extend(result.get("step_timings", []))
        acc_steps += result.get("steps", 0)
        acc_tokens_used += result.get("tokens_used", 0)
        acc_input_tokens += result.get("input_tokens", 0)
        acc_output_tokens += result.get("output_tokens", 0)

        response = result.get("response", "")

        # Decide whether to continue: need remaining turns, a question, AND no
        # tool calls this round (tool use followed by a question is "anything else?" — stop)
        rounds_remaining = (max_user_turns - n_user_turns) > 0
        if not rounds_remaining:
            break
        if not _looks_like_question(response):
            break
        if round_tools:
            # Agent acted AND asked — treat as done
            break

        # Simulate user reply and extend the message history
        user_reply = _simulate_user_reply(task, response)
        n_user_turns += 1
        # Build next-round message list: prior messages + assistant turn + user reply
        messages = list(result.get("messages", messages)) + [
            {"role": "user", "content": user_reply}
        ]

    latency_ms = int((time.time() - start) * 1000)

    # Expose accumulated values as result fields for verifier / EvalResult building
    result["tools_called"] = acc_tools_called
    result["step_timings"] = acc_step_timings
    result["steps"] = acc_steps
    result["tokens_used"] = acc_tokens_used
    result["input_tokens"] = acc_input_tokens
    result["output_tokens"] = acc_output_tokens

    # --- Verify ----------------------------------------------------------
    verifier_type = task.get("verifier", "tool_call_check")
    if verifier_type == "tool_call_check":
        verifier = ToolCallVerifier(
            required_tools=expected.get("tools", []),
            required_params=expected.get("required_params", {}),
        )
    else:
        verifier = LLMJudgeVerifier(
            instruction=task["instruction"],
            criteria=expected.get("criteria", ""),
        )

    agent_output = {
        "response": result.get("response", ""),
        "tools_called": result.get("tools_called", []),
    }
    vresult = verifier.verify(agent_output)

    # Push eval score to Langfuse trace
    _push_score(langfuse_handler, vresult.score, vresult.reason)
    trace_url = _trace_url(langfuse_handler)

    in_tok  = result.get("input_tokens",  0)
    out_tok = result.get("output_tokens", 0)
    model   = _model

    eval_result = EvalResult(
        task_id=task["id"],
        domain=task["domain"],
        skill_name=skill_name if skill_path else None,
        skill_version=None,
        score=vresult.score,
        steps=result.get("steps", 0),
        tools_called=[t["name"] for t in result.get("tools_called", [])],
        tool_params={t["name"]: t.get("params", {}) for t in result.get("tools_called", [])},
        langsmith_run_id=trace_url or "",
        passed_verifier=vresult.passed,
        judge_reasoning=vresult.reason,
        latency_ms=latency_ms,
        tokens_used=result.get("tokens_used", 0),
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=compute_cost(model, in_tok, out_tok),
    )

    # --- SQLite trajectory (lightweight local supplement) ----------------
    try:
        tools_called_raw = result.get("tools_called", [])
        failure_mode = classify_failure(
            tools_called=tools_called_raw,
            required_tools=expected.get("tools", []),
            required_params=expected.get("required_params", {}),
        ) if not vresult.passed else None

        steps_data = [
            TrajectoryStep(
                run_id=run_id, task_id=task["id"],
                skill_name=eval_result.skill_name,
                condition=condition, step_num=i, node="tools",
                tool_name=timing.get("tool"),
                tool_params=tools_called_raw[i].get("params") if i < len(tools_called_raw) else None,
                tool_result=None,
                latency_ms=timing.get("latency_ms", 0),
                tokens=timing.get("tokens", 0),
            )
            for i, timing in enumerate(result.get("step_timings", []))
        ]
        save_run(TrajectoryRun(
            run_id=run_id, task_id=task["id"],
            skill_name=eval_result.skill_name,
            condition=condition, score=vresult.score,
            passed=vresult.passed, failure_mode=failure_mode,
            steps=steps_data, langsmith_url=trace_url,
        ))
    except Exception:
        pass

    return eval_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--skill", default=None)
    parser.add_argument("--condition", default="no_skill")
    parser.add_argument("--mock-mcp-url", default=os.environ.get("MOCK_MCP_URL", "http://localhost:8000"))
    args = parser.parse_args()

    result = run_task(args.task, args.skill, args.condition, args.mock_mcp_url)
    print(json.dumps(dataclasses.asdict(result), indent=2))
