# eval/verifiers/llm_judge.py
import os
import json
import statistics
import anthropic
from eval.verifiers.base import Verifier, VerifierResult

JUDGE_PROMPT = """You are evaluating a travel agent's response.

Task instruction: {instruction}
Agent response: {response}

Score the response from 0.0 to 1.0 where:
- 1.0: Complete, accurate, directly addresses the task
- 0.75: Mostly good with minor gaps
- 0.5: Partially addresses the task
- 0.25: Attempted but largely off
- 0.0: Completely wrong or failed

Reply with only a JSON object: {{"score": 0.0, "reasoning": "..."}}"""


class LLMJudgeVerifier(Verifier):
    """Runs the judge 3 times and averages to reduce variance."""

    def __init__(self, instruction: str, runs: int = 3):
        self.instruction = instruction
        self.runs = runs
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _judge_once(self, response: str):
        prompt = JUDGE_PROMPT.format(instruction=self.instruction, response=response)
        msg = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        data = json.loads(raw)
        return float(data["score"]), data["reasoning"]

    def verify(self, agent_output: dict) -> VerifierResult:
        response = agent_output.get("response", "")
        scores = []
        reasonings = []
        for _ in range(self.runs):
            try:
                score, reasoning = self._judge_once(response)
                scores.append(score)
                reasonings.append(reasoning)
            except Exception as e:
                scores.append(0.0)
                reasonings.append(f"judge error: {e}")

        avg = statistics.mean(scores)
        std = statistics.stdev(scores) if len(scores) > 1 else 0.0
        combined_reason = f"avg={avg:.2f} std={std:.2f} | {reasonings[0]}"
        return VerifierResult(avg >= 0.5, avg, combined_reason)
