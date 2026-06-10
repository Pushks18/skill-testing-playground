# eval/verifiers/llm_judge.py
import os
import json
import re
import statistics
import openai
from eval.verifiers.base import Verifier, VerifierResult

JUDGE_PROMPT = """You are evaluating a travel agent's response.

Task instruction: {instruction}
{criteria_block}
Agent response: {response}

Score the response from 0.0 to 1.0 where:
- 1.0: Complete, accurate, directly addresses the task and all criteria
- 0.75: Mostly good with minor gaps
- 0.5: Partially addresses the task
- 0.25: Attempted but largely off
- 0.0: Completely wrong or failed

Reply with only a JSON object: {{"score": 0.0, "reasoning": "..."}}
Keep reasoning under 50 words."""


def _parse_judge_output(raw: str) -> tuple[float, str]:
    """Parse the judge's JSON, salvaging the score from truncated output.

    The judge sometimes hits the completion cap mid-reasoning, leaving an
    unterminated JSON string; the score field comes first, so it survives
    truncation and a regex can recover it.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
        return float(data["score"]), str(data.get("reasoning", ""))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        m = re.search(r'"score"\s*:\s*([01](?:\.\d+)?)', raw)
        if m:
            return float(m.group(1)), "(reasoning truncated)"
        raise ValueError(f"unparseable judge output: {raw[:120]!r}")


class LLMJudgeVerifier(Verifier):
    """Runs the judge 3 times and averages to reduce variance.

    Errored judge calls are retried once and otherwise EXCLUDED from the
    average — a parse/API failure is eval-infra noise, not evidence the
    agent's response was bad. Scoring failures as 0.0 was silently
    inflating regression counts in A/B runs.
    """

    def __init__(self, instruction: str, criteria: str = "", runs: int = 3):
        self.instruction = instruction
        self.criteria = criteria
        self.runs = runs
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = openai.OpenAI(
                api_key=os.environ["OPENROUTER_API_KEY"],
                base_url="https://openrouter.ai/api/v1",
                timeout=60.0,
                max_retries=2,
            )
        return self._client

    def _judge_once(self, response: str):
        criteria_block = f"Pass criteria: {self.criteria}\n" if self.criteria else ""
        prompt = JUDGE_PROMPT.format(
            instruction=self.instruction,
            criteria_block=criteria_block,
            response=response,
        )
        msg = self.client.chat.completions.create(
            model="google/gemini-2.5-flash",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.choices[0].message.content.strip()
        return _parse_judge_output(raw)

    def verify(self, agent_output: dict) -> VerifierResult:
        response = agent_output.get("response", "")
        scores = []
        reasonings = []
        errors = []
        for _ in range(self.runs):
            for attempt in range(2):  # one retry per run
                try:
                    score, reasoning = self._judge_once(response)
                    scores.append(score)
                    reasonings.append(reasoning)
                    break
                except Exception as e:
                    if attempt == 1:
                        errors.append(f"judge error: {e}")

        if not scores:
            # Every run failed — infra problem, not an agent failure. Surface
            # it loudly instead of pretending the agent scored 0.
            return VerifierResult(False, 0.0, f"JUDGE_INFRA_FAILURE: {'; '.join(errors)}")

        avg = statistics.mean(scores)
        std = statistics.stdev(scores) if len(scores) > 1 else 0.0
        note = f" | {len(errors)} errored run(s) excluded" if errors else ""
        combined_reason = f"avg={avg:.2f} std={std:.2f} | {reasonings[0]}{note}"
        return VerifierResult(avg >= 0.5, avg, combined_reason)
