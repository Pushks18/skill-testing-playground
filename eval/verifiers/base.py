# eval/verifiers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class VerifierResult:
    passed: bool
    score: float
    reason: str

class Verifier(ABC):
    @abstractmethod
    def verify(self, agent_output: dict) -> VerifierResult:
        ...
