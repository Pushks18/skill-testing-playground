# eval/verifiers/tool_call.py
from eval.verifiers.base import Verifier, VerifierResult

class ToolCallVerifier(Verifier):
    def __init__(self, required_tools, required_params):
        self.required_tools = required_tools
        self.required_params = required_params

    def verify(self, agent_output: dict) -> VerifierResult:
        tools_called = {t["name"]: t.get("params", {}) for t in agent_output.get("tools_called", [])}
        missing_tools = [t for t in self.required_tools if t not in tools_called]
        if missing_tools:
            return VerifierResult(False, 0.0, f"Missing required tools: {missing_tools}")

        missing_params = []
        for tool, params in self.required_params.items():
            if tool in tools_called:
                for p in params:
                    if p not in tools_called[tool]:
                        missing_params.append(f"{tool}.{p}")

        if missing_params:
            total_params = sum(len(v) for v in self.required_params.values())
            score = max(0.0, 1.0 - len(missing_params) / max(total_params, 1))
            return VerifierResult(False, score, f"Missing params: {missing_params}")

        return VerifierResult(True, 1.0, "All required tools and params present")
