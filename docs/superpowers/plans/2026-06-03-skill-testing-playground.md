# Skill Testing Playground Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Week 1 MVP eval platform that A/B tests travel-agent skills, gates PRs via tiered thresholds, measures trigger P/R, and exposes a leaderboard.

**Architecture:** LangGraph agent runner posts traces to LangSmith; BenchFlow-format task bank drives A/B comparison; a tiered gate (T1 hard block / T2 soft block / T3 warn) runs in GitHub Actions on every skill PR. Optimizer and pyramid analyzer are CLI tools that propose but never auto-commit.

**Tech Stack:** Python 3.11, LangGraph, LangSmith, FastAPI (mock MCP), pytest, anthropic SDK, PyYAML, tomllib, asyncio, GitHub Actions

---

## File Map

```
skill-testing-playground/
├── pyproject.toml
├── requirements.txt
├── .env.example
├── eval/
│   ├── schemas.py                  # dataclasses: EvalResult, ABResult, GateDecision, SkillCoverageMetrics, SkillMeta
│   ├── run_task.py                 # single-task runner; LangSmith-traced
│   ├── ab_compare.py               # async A/B harness; writes ab_results.json
│   ├── gate_check.py               # reads ab_results.json; exits 1 on T1/T2
│   ├── trigger_eval.py             # trigger P/R across labeled_requests.json
│   ├── leaderboard.py              # aggregates all ab_results.json files
│   ├── gate_thresholds.yaml        # versioned threshold config
│   ├── mock_mcp/
│   │   └── server.py               # FastAPI mock for all approved MCP tools
│   ├── verifiers/
│   │   ├── base.py                 # abstract Verifier
│   │   ├── tool_call.py            # ToolCallVerifier
│   │   └── llm_judge.py            # LLMJudgeVerifier (3x averaged)
│   ├── security/
│   │   ├── approved_tools.json
│   │   ├── promptfoo_skill_scan.yaml
│   │   ├── skill_security_provider.py
│   │   └── plugins/mcp_scope_check.py
│   └── optimizer/
│       ├── optimizer.py            # pseudo-GRPO loop
│       └── variant_strategies.py  # 5 strategy prompts
├── pyramid/
│   └── analyze.py                  # atomic/abstract extraction suggestions
├── agent/
│   └── travel_agent.py             # LangGraph agent with optional skill injection
├── tasks/                          # 20 BenchFlow task directories
│   ├── flight-search-001/
│   │   ├── instruction.md
│   │   ├── task.toml
│   │   ├── environment/skills/flight-search/SKILL.md
│   │   ├── solution/solve.sh
│   │   └── tests/test_outputs.py
│   └── ... (19 more, same structure)
├── skills/
│   ├── atomic/
│   ├── concrete/flight-search/SKILL.md
│   └── abstract/
├── trigger/
│   └── labeled_requests.json       # 30 labeled trigger test cases
├── .github/
│   ├── workflows/eval_skill.yml
│   └── scripts/detect_skill.py
└── tests/
    ├── test_schemas.py
    ├── test_verifiers.py
    ├── test_gate_check.py
    └── test_mock_mcp.py
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `.env.example`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "skill-testing-playground"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "langsmith>=0.2.0",
    "langchain>=0.3.0",
    "langgraph>=0.2.0",
    "langchain-anthropic>=0.3.0",
    "openinference-instrumentation-langchain>=0.1.0",
    "opentelemetry-sdk>=1.20.0",
    "fastapi>=0.110.0",
    "uvicorn>=0.29.0",
    "httpx>=0.27.0",
    "anthropic>=0.34.0",
    "pyyaml>=6.0",
    "tomli>=2.0.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "anyio>=4.0.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write requirements.txt**

```
langsmith>=0.2.0
langchain>=0.3.0
langgraph>=0.2.0
langchain-anthropic>=0.3.0
openinference-instrumentation-langchain>=0.1.0
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp-proto-http>=1.20.0
fastapi>=0.110.0
uvicorn>=0.29.0
httpx>=0.27.0
anthropic>=0.34.0
pyyaml>=6.0
tomli>=2.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
anyio>=4.0.0
```

- [ ] **Step 3: Write .env.example**

```
ANTHROPIC_API_KEY=sk-ant-...
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=skill-testing-playground
LANGCHAIN_TRACING_V2=true
MOCK_MCP_URL=http://localhost:8000
```

- [ ] **Step 4: Install dependencies**

```bash
cd /Users/pushkaraj/Documents/skill-testing-playground
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Expected: no errors

- [ ] **Step 5: Init git and commit**

```bash
git init
git add pyproject.toml requirements.txt .env.example
git commit -m "chore: project scaffold"
```

---

### Task 2: Data Schemas

**Files:**
- Create: `eval/schemas.py`
- Create: `tests/test_schemas.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_schemas.py
from eval.schemas import EvalResult, ABResult, GateDecision, SkillCoverageMetrics

def test_ab_result_delta():
    no_skill = EvalResult(
        task_id="t1", domain="flight_search", skill_name=None,
        skill_version=None, score=0.5, steps=3, tools_called=[],
        tool_params={}, langsmith_run_id="r1", passed_verifier=True,
        judge_reasoning=None, latency_ms=100, tokens_used=200,
    )
    with_skill = EvalResult(
        task_id="t1", domain="flight_search", skill_name="flight-search",
        skill_version="v1.0", score=0.8, steps=2, tools_called=["search_flights"],
        tool_params={"origin": "JFK"}, langsmith_run_id="r2",
        passed_verifier=True, judge_reasoning=None, latency_ms=90, tokens_used=180,
    )
    ab = ABResult.from_pair("flight-search", no_skill, with_skill, task_weight=2.0)
    assert abs(ab.delta - 0.3) < 0.001
    assert ab.regression is False
    assert ab.step_delta == -1

def test_gate_decision_fields():
    d = GateDecision(
        verdict="BLOCK", tier=1, weighted_delta=-0.1,
        regression_rate=0.35, flagged_tasks=["t1"],
        langsmith_experiment_url="https://example.com",
        override_allowed=False,
    )
    assert d.override_allowed is False
```

- [ ] **Step 2: Run — expect ImportError**

```bash
pytest tests/test_schemas.py -v
```

- [ ] **Step 3: Write eval/schemas.py**

```python
# eval/schemas.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional

@dataclass
class EvalResult:
    task_id: str
    domain: str
    skill_name: Optional[str]
    skill_version: Optional[str]
    score: float
    steps: int
    tools_called: list[str]
    tool_params: dict
    langsmith_run_id: str
    passed_verifier: bool
    judge_reasoning: Optional[str]
    latency_ms: int
    tokens_used: int

@dataclass
class ABResult:
    skill_name: str
    task_id: str
    domain: str
    task_weight: float
    no_skill: EvalResult
    with_skill: EvalResult
    delta: float
    delta_significant: bool
    regression: bool
    step_delta: int
    token_delta: int

    @classmethod
    def from_pair(
        cls,
        skill_name: str,
        no_skill: EvalResult,
        with_skill: EvalResult,
        task_weight: float,
    ) -> "ABResult":
        delta = with_skill.score - no_skill.score
        return cls(
            skill_name=skill_name,
            task_id=no_skill.task_id,
            domain=no_skill.domain,
            task_weight=task_weight,
            no_skill=no_skill,
            with_skill=with_skill,
            delta=delta,
            delta_significant=abs(delta) > 0.05 and True,
            regression=delta < 0,
            step_delta=with_skill.steps - no_skill.steps,
            token_delta=with_skill.tokens_used - no_skill.tokens_used,
        )

@dataclass
class GateDecision:
    verdict: Literal["PASS", "WARN", "SOFT_BLOCK", "BLOCK"]
    tier: int
    weighted_delta: float
    regression_rate: float
    flagged_tasks: list[str]
    langsmith_experiment_url: str
    override_allowed: bool

@dataclass
class SkillCoverageMetrics:
    skill_name: str
    trigger_precision: float
    trigger_recall: float
    no_trigger_precision: float
    coverage_precision: float
    coverage_recall: float
    optimizer_strategy: str

@dataclass
class SkillMeta:
    name: str
    layer: int
    path: str
    depends_on: list[str]
    abstracted_by: list[str]
    eval_score: Optional[float]
    coverage_metrics: Optional[SkillCoverageMetrics]
    last_eval: Optional[str]
    version: str
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_schemas.py -v
```

- [ ] **Step 5: Commit**

```bash
git add eval/schemas.py tests/test_schemas.py
git commit -m "feat: data schemas for eval pipeline"
```

---

### Task 3: Mock MCP Server

**Files:**
- Create: `eval/mock_mcp/server.py`
- Create: `eval/mock_mcp/__init__.py`
- Create: `tests/test_mock_mcp.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_mock_mcp.py
import pytest
import httpx
import subprocess
import time
import signal
import os

@pytest.fixture(scope="module")
def mcp_server():
    proc = subprocess.Popen(
        ["python", "eval/mock_mcp/server.py"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)
    yield "http://localhost:8000"
    proc.send_signal(signal.SIGTERM)

def test_search_flights(mcp_server):
    r = httpx.post(f"{mcp_server}/search_flights",
                   json={"origin": "JFK", "destination": "LAX", "date": "2026-07-01"})
    assert r.status_code == 200
    data = r.json()
    assert "flights" in data
    assert len(data["flights"]) > 0
    assert "price" in data["flights"][0]

def test_search_hotels(mcp_server):
    r = httpx.post(f"{mcp_server}/search_hotels",
                   json={"location": "Los Angeles", "check_in": "2026-07-01", "check_out": "2026-07-03"})
    assert r.status_code == 200
    assert "hotels" in r.json()

def test_check_availability(mcp_server):
    r = httpx.post(f"{mcp_server}/check_availability",
                   json={"resource_id": "FL123", "date": "2026-07-01"})
    assert r.status_code == 200
    assert "available" in r.json()

def test_create_booking(mcp_server):
    r = httpx.post(f"{mcp_server}/create_booking",
                   json={"flight_id": "FL123", "passenger": {"name": "Alice", "dob": "1990-01-01"}})
    assert r.status_code == 200
    assert "booking_id" in r.json()
```

- [ ] **Step 2: Run — expect connection error**

```bash
pytest tests/test_mock_mcp.py -v
```

- [ ] **Step 3: Write eval/mock_mcp/server.py**

```python
# eval/mock_mcp/server.py
import uuid
import random
from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Mock Mondee MCP")

class FlightSearch(BaseModel):
    origin: str
    destination: str
    date: str
    passengers: int = 1

class HotelSearch(BaseModel):
    location: str
    check_in: str
    check_out: str
    guests: int = 1

class AvailabilityCheck(BaseModel):
    resource_id: str
    date: str

class FareRulesRequest(BaseModel):
    flight_id: str

class PassengerValidation(BaseModel):
    name: str
    dob: str
    passport: Optional[str] = None

class BookingRequest(BaseModel):
    flight_id: Optional[str] = None
    hotel_id: Optional[str] = None
    passenger: dict

class ModifyBookingRequest(BaseModel):
    booking_id: str
    changes: dict

class CancelBookingRequest(BaseModel):
    booking_id: str

class GetItineraryRequest(BaseModel):
    booking_id: str

AIRLINES = ["Delta", "United", "American", "JetBlue", "Southwest"]
HOTEL_CHAINS = ["Marriott", "Hilton", "Hyatt", "IHG", "Wyndham"]

@app.post("/search_flights")
def search_flights(req: FlightSearch):
    flights = [
        {
            "flight_id": f"FL{random.randint(100,999)}",
            "airline": random.choice(AIRLINES),
            "origin": req.origin,
            "destination": req.destination,
            "date": req.date,
            "departure": f"{random.randint(6,20):02d}:{random.choice(['00','30'])}",
            "duration_min": random.randint(90, 360),
            "price": round(random.uniform(150, 900), 2),
            "seats_available": random.randint(1, 30),
            "cabin": "economy",
        }
        for _ in range(random.randint(3, 6))
    ]
    return {"flights": flights, "currency": "USD"}

@app.post("/search_hotels")
def search_hotels(req: HotelSearch):
    hotels = [
        {
            "hotel_id": f"HT{random.randint(100,999)}",
            "name": f"{random.choice(HOTEL_CHAINS)} {req.location}",
            "location": req.location,
            "check_in": req.check_in,
            "check_out": req.check_out,
            "price_per_night": round(random.uniform(80, 500), 2),
            "stars": random.randint(3, 5),
            "available": True,
        }
        for _ in range(random.randint(3, 5))
    ]
    return {"hotels": hotels, "currency": "USD"}

@app.post("/check_availability")
def check_availability(req: AvailabilityCheck):
    return {"resource_id": req.resource_id, "date": req.date, "available": random.random() > 0.2}

@app.post("/get_fare_rules")
def get_fare_rules(req: FareRulesRequest):
    return {
        "flight_id": req.flight_id,
        "cancellation": "Free within 24h; $150 fee after",
        "changes": "$75 change fee applies",
        "baggage": "1 carry-on included; checked bag $35",
        "refundable": random.random() > 0.5,
    }

@app.post("/validate_passenger")
def validate_passenger(req: PassengerValidation):
    return {"valid": True, "name": req.name, "warnings": []}

@app.post("/create_booking")
def create_booking(req: BookingRequest):
    return {
        "booking_id": f"BK{uuid.uuid4().hex[:8].upper()}",
        "status": "confirmed",
        "flight_id": req.flight_id,
        "hotel_id": req.hotel_id,
        "total_price": round(random.uniform(200, 1500), 2),
    }

@app.post("/modify_booking")
def modify_booking(req: ModifyBookingRequest):
    return {"booking_id": req.booking_id, "status": "modified", "changes_applied": req.changes}

@app.post("/cancel_booking")
def cancel_booking(req: CancelBookingRequest):
    return {"booking_id": req.booking_id, "status": "cancelled", "refund_amount": round(random.uniform(0, 500), 2)}

@app.post("/get_itinerary")
def get_itinerary(req: GetItineraryRequest):
    return {
        "booking_id": req.booking_id,
        "itinerary": [
            {"type": "flight", "details": "JFK → LAX, 2026-07-01 09:00"},
            {"type": "hotel", "details": "Marriott LA, 2026-07-01 to 2026-07-03"},
        ],
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

```python
# eval/mock_mcp/__init__.py
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_mock_mcp.py -v
```

- [ ] **Step 5: Commit**

```bash
git add eval/mock_mcp/ tests/test_mock_mcp.py
git commit -m "feat: mock MCP server with all approved travel tools"
```

---

### Task 4: Verifiers

**Files:**
- Create: `eval/verifiers/base.py`
- Create: `eval/verifiers/tool_call.py`
- Create: `eval/verifiers/llm_judge.py`
- Create: `eval/verifiers/__init__.py`
- Create: `tests/test_verifiers.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_verifiers.py
import pytest
from eval.verifiers.tool_call import ToolCallVerifier
from eval.verifiers.llm_judge import LLMJudgeVerifier

def test_tool_call_verifier_pass():
    v = ToolCallVerifier(
        required_tools=["search_flights"],
        required_params={"search_flights": ["origin", "destination", "date"]},
    )
    result = v.verify(
        agent_output={"response": "Found 3 flights", "tools_called": [
            {"name": "search_flights", "params": {"origin": "JFK", "destination": "LAX", "date": "2026-07-01"}}
        ]}
    )
    assert result.passed is True
    assert result.score == 1.0

def test_tool_call_verifier_missing_tool():
    v = ToolCallVerifier(
        required_tools=["search_flights"],
        required_params={"search_flights": ["origin"]},
    )
    result = v.verify(agent_output={"response": "I searched", "tools_called": []})
    assert result.passed is False
    assert result.score == 0.0
    assert "search_flights" in result.reason

def test_tool_call_verifier_missing_param():
    v = ToolCallVerifier(
        required_tools=["search_flights"],
        required_params={"search_flights": ["origin", "destination", "date"]},
    )
    result = v.verify(agent_output={"response": "ok", "tools_called": [
        {"name": "search_flights", "params": {"origin": "JFK"}}
    ]})
    assert result.passed is False
    assert result.score < 1.0
```

- [ ] **Step 2: Run — expect ImportError**

```bash
pytest tests/test_verifiers.py -v
```

- [ ] **Step 3: Write base.py**

```python
# eval/verifiers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class VerifierResult:
    passed: bool
    score: float          # 0.0–1.0
    reason: str

class Verifier(ABC):
    @abstractmethod
    def verify(self, agent_output: dict) -> VerifierResult:
        ...
```

- [ ] **Step 4: Write tool_call.py**

```python
# eval/verifiers/tool_call.py
from eval.verifiers.base import Verifier, VerifierResult

class ToolCallVerifier(Verifier):
    def __init__(self, required_tools: list[str], required_params: dict[str, list[str]]):
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
                called_params = tools_called[tool]
                for p in params:
                    if p not in called_params:
                        missing_params.append(f"{tool}.{p}")

        if missing_params:
            score = 1.0 - (len(missing_params) / max(sum(len(v) for v in self.required_params.values()), 1))
            return VerifierResult(False, max(0.0, score), f"Missing params: {missing_params}")

        return VerifierResult(True, 1.0, "All required tools and params present")
```

- [ ] **Step 5: Write llm_judge.py**

```python
# eval/verifiers/llm_judge.py
import os
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

    def _judge_once(self, response: str) -> tuple[float, str]:
        import json
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
```

```python
# eval/verifiers/__init__.py
from eval.verifiers.tool_call import ToolCallVerifier
from eval.verifiers.llm_judge import LLMJudgeVerifier
```

- [ ] **Step 6: Run tests — expect PASS (tool_call tests only; llm_judge requires API key)**

```bash
pytest tests/test_verifiers.py::test_tool_call_verifier_pass \
       tests/test_verifiers.py::test_tool_call_verifier_missing_tool \
       tests/test_verifiers.py::test_tool_call_verifier_missing_param -v
```

- [ ] **Step 7: Commit**

```bash
git add eval/verifiers/ tests/test_verifiers.py
git commit -m "feat: tool_call and llm_judge verifiers"
```

---

### Task 5: Task Bank (20 BenchFlow Tasks)

**Files:**
- Create: `tasks/flight-search-00{1,2,3,4}/` (4 dirs)
- Create: `tasks/hotel-search-00{1,2,3,4}/` (4 dirs)
- Create: `tasks/booking-flow-00{1,2,3,4}/` (4 dirs)
- Create: `tasks/fare-rules-00{1,2,3}/` (3 dirs)
- Create: `tasks/itinerary-00{1,2,3}/` (3 dirs)
- Create: `tasks/edge-cancel-001/`, `tasks/edge-multileg-001/`, `tasks/edge-datechange-001/`
- Create: `scripts/create_tasks.py` (generator script)

Rather than writing 20 directories by hand, use a generator:

- [ ] **Step 1: Write scripts/create_tasks.py**

```python
#!/usr/bin/env python3
# scripts/create_tasks.py
"""Generates all 20 BenchFlow task directories."""
import os
import pathlib

ROOT = pathlib.Path("tasks")

TASKS = [
    # (task_id, domain, skill, verifier, weight, instruction, required_tools, required_params)
    ("flight-search-001", "flight_search", "flight-search", "tool_call_check", 2.0,
     "Find round-trip flights from JFK to LAX departing 2026-08-10 returning 2026-08-17 for 1 adult.",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),

    ("flight-search-002", "flight_search", "flight-search", "tool_call_check", 2.0,
     "Search for one-way flights from ORD to MIA on 2026-09-05 for 2 passengers.",
     ["search_flights"], {"search_flights": ["origin", "destination", "date", "passengers"]}),

    ("flight-search-003", "flight_search", "flight-search", "tool_call_check", 2.0,
     "Find the cheapest nonstop flights from SFO to JFK next Monday.",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),

    ("flight-search-004", "flight_search", "flight-search", "tool_call_check", 2.0,
     "What flights are available from BOS to SEA on 2026-07-20?",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),

    ("hotel-search-001", "hotel_search", "hotel-search", "tool_call_check", 2.0,
     "Find hotels in Chicago from July 15 to July 18 for 2 guests.",
     ["search_hotels"], {"search_hotels": ["location", "check_in", "check_out"]}),

    ("hotel-search-002", "hotel_search", "hotel-search", "tool_call_check", 2.0,
     "Search for 4-star or higher hotels in Miami Beach for 3 nights starting August 1.",
     ["search_hotels"], {"search_hotels": ["location", "check_in", "check_out"]}),

    ("hotel-search-003", "hotel_search", "hotel-search", "tool_call_check", 2.0,
     "What hotels near LAX are available on the night of September 10?",
     ["search_hotels"], {"search_hotels": ["location", "check_in", "check_out"]}),

    ("hotel-search-004", "hotel_search", "hotel-search", "tool_call_check", 2.0,
     "Find budget hotels in Denver for a week starting 2026-10-01.",
     ["search_hotels"], {"search_hotels": ["location", "check_in", "check_out"]}),

    ("booking-flow-001", "booking_flow", "book-itinerary", "tool_call_check", 3.0,
     "Book flight FL123 for passenger Alice Johnson (DOB 1985-03-15). Confirm the booking.",
     ["create_booking"], {"create_booking": ["flight_id", "passenger"]}),

    ("booking-flow-002", "booking_flow", "book-itinerary", "tool_call_check", 3.0,
     "Complete a hotel booking for HT456 for passenger Bob Smith checking in July 15.",
     ["create_booking"], {"create_booking": ["hotel_id", "passenger"]}),

    ("booking-flow-003", "booking_flow", "book-itinerary", "tool_call_check", 3.0,
     "First check availability for flight FL789 on 2026-08-01, then book it for passenger Carol Davis.",
     ["check_availability", "create_booking"],
     {"check_availability": ["resource_id", "date"], "create_booking": ["flight_id", "passenger"]}),

    ("booking-flow-004", "booking_flow", "book-itinerary", "tool_call_check", 3.0,
     "Validate passenger Eve Wilson (DOB 1992-07-22, passport A1234567) and book flight FL321.",
     ["validate_passenger", "create_booking"],
     {"validate_passenger": ["name", "dob"], "create_booking": ["flight_id", "passenger"]}),

    ("fare-rules-001", "fare_rules", "fare-rules", "llm_judge", 1.0,
     "What are the cancellation and change fees for flight FL555?",
     ["get_fare_rules"], {"get_fare_rules": ["flight_id"]}),

    ("fare-rules-002", "fare_rules", "fare-rules", "llm_judge", 1.0,
     "Is flight FL888 refundable? What is the baggage allowance?",
     ["get_fare_rules"], {"get_fare_rules": ["flight_id"]}),

    ("fare-rules-003", "fare_rules", "fare-rules", "llm_judge", 1.0,
     "Explain the fare conditions for FL200 in plain language.",
     ["get_fare_rules"], {"get_fare_rules": ["flight_id"]}),

    ("itinerary-001", "itinerary_build", "book-itinerary", "llm_judge", 1.5,
     "Build a complete 3-day New York itinerary with flights from LAX and hotel near Times Square.",
     ["search_flights", "search_hotels"],
     {"search_flights": ["origin", "destination", "date"], "search_hotels": ["location", "check_in", "check_out"]}),

    ("itinerary-002", "itinerary_build", "book-itinerary", "llm_judge", 1.5,
     "Retrieve and summarize the itinerary for booking BK12345678.",
     ["get_itinerary"], {"get_itinerary": ["booking_id"]}),

    ("itinerary-003", "itinerary_build", "book-itinerary", "llm_judge", 1.5,
     "Plan a weekend trip from Chicago to Nashville: find flights and a hotel, present as an itinerary.",
     ["search_flights", "search_hotels"],
     {"search_flights": ["origin", "destination", "date"], "search_hotels": ["location", "check_in", "check_out"]}),

    ("edge-cancel-001", "edge_cases", "modify-booking", "tool_call_check", 0.5,
     "Cancel booking BK99887766 and confirm the cancellation.",
     ["cancel_booking"], {"cancel_booking": ["booking_id"]}),

    ("edge-multileg-001", "edge_cases", "flight-search", "tool_call_check", 0.5,
     "Find flights for a multi-leg trip: NYC to Chicago on Aug 5, Chicago to LA on Aug 8.",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),

    ("edge-datechange-001", "edge_cases", "modify-booking", "tool_call_check", 0.5,
     "Change the date on booking BK11223344 to August 20.",
     ["modify_booking"], {"modify_booking": ["booking_id", "changes"]}),
]

TASK_TOML_TEMPLATE = """\
[task]
id = "{task_id}"
domain = "{domain}"
skill = "{skill}"
verifier = "{verifier}"
weight = {weight}

[expected]
tools = {tools}
required_params = {required_params}
"""

INSTRUCTION_TEMPLATE = "{instruction}\n"

TEST_TOOL_CALL_TEMPLATE = """\
import json, pathlib, pytest

def load_output():
    p = pathlib.Path("task_output.json")
    if not p.exists():
        pytest.skip("No task_output.json found")
    return json.loads(p.read_text())

def test_required_tools():
    output = load_output()
    tools_called = {{t["name"] for t in output.get("tools_called", [])}}
    required = {required_tools}
    missing = [t for t in required if t not in tools_called]
    assert not missing, f"Missing tools: {{missing}}"

def test_required_params():
    output = load_output()
    tools_map = {{t["name"]: t.get("params", {{}}) for t in output.get("tools_called", [])}}
    required_params = {required_params}
    for tool, params in required_params.items():
        if tool in tools_map:
            for p in params:
                assert p in tools_map[tool], f"Missing param {{p}} in {{tool}}"
"""

TEST_LLM_JUDGE_TEMPLATE = """\
import json, pathlib, pytest

def load_output():
    p = pathlib.Path("task_output.json")
    if not p.exists():
        pytest.skip("No task_output.json found")
    return json.loads(p.read_text())

def test_score_above_threshold():
    output = load_output()
    score = output.get("score", 0.0)
    assert score >= 0.5, f"LLM judge score {{score}} below 0.5 threshold"

def test_has_response():
    output = load_output()
    assert output.get("response"), "No response in output"
"""

SOLVE_SH_TEMPLATE = """\
#!/bin/bash
# Oracle: expected tool calls for {task_id}
echo "Expected tools: {tools}"
"""


def quote_list(lst):
    return "[" + ", ".join(f'"{x}"' for x in lst) + "]"


def format_required_params(rp):
    pairs = ", ".join(f'"{k}": {quote_list(v)}' for k, v in rp.items())
    return "{" + pairs + "}"


for row in TASKS:
    task_id, domain, skill, verifier, weight, instruction, req_tools, req_params = row
    task_dir = ROOT / task_id
    (task_dir / "environment" / "skills" / skill).mkdir(parents=True, exist_ok=True)
    (task_dir / "solution").mkdir(exist_ok=True)
    (task_dir / "tests").mkdir(exist_ok=True)

    (task_dir / "instruction.md").write_text(INSTRUCTION_TEMPLATE.format(instruction=instruction))

    toml_content = TASK_TOML_TEMPLATE.format(
        task_id=task_id, domain=domain, skill=skill, verifier=verifier,
        weight=weight, tools=quote_list(req_tools),
        required_params=format_required_params(req_params),
    )
    (task_dir / "task.toml").write_text(toml_content)

    (task_dir / "solution" / "solve.sh").write_text(
        SOLVE_SH_TEMPLATE.format(task_id=task_id, tools=", ".join(req_tools))
    )
    os.chmod(task_dir / "solution" / "solve.sh", 0o755)

    skill_md = f"# {skill}\n\nSkill stub for {domain} tasks.\n"
    (task_dir / "environment" / "skills" / skill / "SKILL.md").write_text(skill_md)

    if verifier == "tool_call_check":
        test_content = TEST_TOOL_CALL_TEMPLATE.format(
            required_tools=req_tools,
            required_params=req_params,
        )
    else:
        test_content = TEST_LLM_JUDGE_TEMPLATE

    (task_dir / "tests" / "test_outputs.py").write_text(test_content)

print(f"Created {len(TASKS)} task directories in tasks/")
```

- [ ] **Step 2: Run the generator**

```bash
python scripts/create_tasks.py
```

Expected: `Created 21 task directories in tasks/`

- [ ] **Step 3: Verify structure**

```bash
ls tasks/ | wc -l   # expect 21
ls tasks/flight-search-001/
# instruction.md  task.toml  environment/  solution/  tests/
```

- [ ] **Step 4: Commit**

```bash
git add tasks/ scripts/create_tasks.py
git commit -m "feat: 20 BenchFlow-format task directories"
```

---

### Task 6: LangGraph Travel Agent + LangSmith Tracing

**Files:**
- Create: `agent/travel_agent.py`
- Create: `agent/__init__.py`
- Create: `eval/run_task.py`

- [ ] **Step 1: Write agent/travel_agent.py**

```python
# agent/travel_agent.py
"""LangGraph travel agent with optional skill injection via system prompt."""
from __future__ import annotations
import os
import time
import httpx
from typing import TypedDict, Optional, Annotated
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
import operator

MOCK_MCP_URL = os.environ.get("MOCK_MCP_URL", "http://localhost:8000")

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    tools_called: list[dict]
    response: str
    steps: int
    tokens_used: int

def make_mcp_tools(base_url: str):
    @tool
    def search_flights(origin: str, destination: str, date: str, passengers: int = 1) -> dict:
        """Search for available flights."""
        r = httpx.post(f"{base_url}/search_flights",
                       json={"origin": origin, "destination": destination,
                             "date": date, "passengers": passengers}, timeout=10)
        return r.json()

    @tool
    def search_hotels(location: str, check_in: str, check_out: str, guests: int = 1) -> dict:
        """Search for available hotels."""
        r = httpx.post(f"{base_url}/search_hotels",
                       json={"location": location, "check_in": check_in,
                             "check_out": check_out, "guests": guests}, timeout=10)
        return r.json()

    @tool
    def check_availability(resource_id: str, date: str) -> dict:
        """Check if a flight or hotel is available."""
        r = httpx.post(f"{base_url}/check_availability",
                       json={"resource_id": resource_id, "date": date}, timeout=10)
        return r.json()

    @tool
    def get_fare_rules(flight_id: str) -> dict:
        """Get fare rules for a flight."""
        r = httpx.post(f"{base_url}/get_fare_rules", json={"flight_id": flight_id}, timeout=10)
        return r.json()

    @tool
    def validate_passenger(name: str, dob: str, passport: str = None) -> dict:
        """Validate passenger information."""
        r = httpx.post(f"{base_url}/validate_passenger",
                       json={"name": name, "dob": dob, "passport": passport}, timeout=10)
        return r.json()

    @tool
    def create_booking(passenger: dict, flight_id: str = None, hotel_id: str = None) -> dict:
        """Create a booking for a flight or hotel."""
        r = httpx.post(f"{base_url}/create_booking",
                       json={"flight_id": flight_id, "hotel_id": hotel_id,
                             "passenger": passenger}, timeout=10)
        return r.json()

    @tool
    def modify_booking(booking_id: str, changes: dict) -> dict:
        """Modify an existing booking."""
        r = httpx.post(f"{base_url}/modify_booking",
                       json={"booking_id": booking_id, "changes": changes}, timeout=10)
        return r.json()

    @tool
    def cancel_booking(booking_id: str) -> dict:
        """Cancel a booking."""
        r = httpx.post(f"{base_url}/cancel_booking", json={"booking_id": booking_id}, timeout=10)
        return r.json()

    @tool
    def get_itinerary(booking_id: str) -> dict:
        """Retrieve a booking itinerary."""
        r = httpx.post(f"{base_url}/get_itinerary", json={"booking_id": booking_id}, timeout=10)
        return r.json()

    return [search_flights, search_hotels, check_availability, get_fare_rules,
            validate_passenger, create_booking, modify_booking, cancel_booking, get_itinerary]


def build_travel_agent(skill_content: Optional[str] = None, mock_mcp_url: str = MOCK_MCP_URL):
    tools = make_mcp_tools(mock_mcp_url)
    tool_map = {t.name: t for t in tools}

    system_prompt = "You are a helpful travel assistant. Use the available tools to help users with flight searches, hotel bookings, and travel planning."
    if skill_content:
        system_prompt += f"\n\n## Skill Instructions\n{skill_content}"

    llm = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    ).bind_tools(tools)

    def agent_node(state: AgentState) -> dict:
        msgs = [SystemMessage(content=system_prompt)] + state["messages"]
        response = llm.invoke(msgs)
        tools_called = state.get("tools_called", [])
        steps = state.get("steps", 0) + 1
        tokens = state.get("tokens_used", 0) + (response.usage_metadata or {}).get("total_tokens", 0)
        return {
            "messages": [response],
            "tools_called": tools_called,
            "steps": steps,
            "tokens_used": tokens,
        }

    def tool_node(state: AgentState) -> dict:
        last = state["messages"][-1]
        tool_results = []
        tools_called = list(state.get("tools_called", []))
        for tc in last.tool_calls:
            fn = tool_map.get(tc["name"])
            if fn:
                result = fn.invoke(tc["args"])
                tools_called.append({"name": tc["name"], "params": tc["args"]})
                tool_results.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        return {"messages": tool_results, "tools_called": tools_called}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    def format_response(state: AgentState) -> dict:
        last = state["messages"][-1]
        return {"response": last.content if hasattr(last, "content") else str(last)}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("format", format_response)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: "format"})
    graph.add_edge("tools", "agent")
    graph.add_edge("format", END)

    return graph.compile()
```

```python
# agent/__init__.py
```

- [ ] **Step 2: Write eval/run_task.py**

```python
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

LangChainInstrumentor().instrument(tracer_provider=TracerProvider())
ls_client = langsmith.Client()


def load_task(task_path: pathlib.Path) -> dict:
    with open(task_path / "task.toml", "rb") as f:
        meta = tomllib.load(f)
    instruction = (task_path / "instruction.md").read_text().strip()
    return {**meta["task"], "expected": meta.get("expected", {}), "instruction": instruction}


def load_skill(skill_path: pathlib.Path | None) -> str | None:
    if skill_path is None:
        return None
    skill_file = skill_path / "SKILL.md"
    if skill_file.exists():
        return skill_file.read_text()
    return None


@langsmith.traceable(name="skill_eval")
def run_task(
    task_path: str,
    skill_path: str | None = None,
    condition: str = "no_skill",
    mock_mcp_url: str = "http://localhost:8000",
) -> EvalResult:
    task_dir = pathlib.Path(task_path)
    skill_dir = pathlib.Path(skill_path) if skill_path else None

    task = load_task(task_dir)
    skill_content = load_skill(skill_dir)

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
```

- [ ] **Step 3: Smoke test (requires running mock MCP and API key)**

```bash
# Terminal 1:
python eval/mock_mcp/server.py &

# Terminal 2:
python eval/run_task.py --task tasks/flight-search-001 --condition no_skill
```

Expected: JSON output with `task_id`, `score`, `tools_called`

- [ ] **Step 4: Commit**

```bash
git add agent/ eval/run_task.py
git commit -m "feat: LangGraph travel agent and single-task runner with LangSmith tracing"
```

---

### Task 7: A/B Harness + Gate Check

**Files:**
- Create: `eval/ab_compare.py`
- Create: `eval/gate_check.py`
- Create: `eval/gate_thresholds.yaml`
- Create: `tests/test_gate_check.py`

- [ ] **Step 1: Write failing gate tests**

```python
# tests/test_gate_check.py
import pytest
from eval.schemas import ABResult, EvalResult, GateDecision
from eval.gate_check import gate_check, compute_weighted_delta

def make_ab(task_id, domain, delta, weight=1.0) -> ABResult:
    base = EvalResult(task_id=task_id, domain=domain, skill_name="test",
                      skill_version="v1", score=0.5, steps=2, tools_called=[],
                      tool_params={}, langsmith_run_id="", passed_verifier=True,
                      judge_reasoning=None, latency_ms=100, tokens_used=100)
    with_s = EvalResult(task_id=task_id, domain=domain, skill_name="test",
                        skill_version="v1", score=0.5 + delta, steps=2, tools_called=[],
                        tool_params={}, langsmith_run_id="", passed_verifier=True,
                        judge_reasoning=None, latency_ms=100, tokens_used=100)
    return ABResult.from_pair("test", base, with_s, task_weight=weight)

def test_pass():
    results = [make_ab(f"t{i}", "flight_search", 0.1, 2.0) for i in range(5)]
    d = gate_check(results)
    assert d.verdict == "PASS"
    assert d.tier == 0

def test_tier1_hard_block_on_negative_weighted_delta():
    results = [make_ab(f"t{i}", "flight_search", -0.1, 2.0) for i in range(5)]
    d = gate_check(results)
    assert d.verdict == "BLOCK"
    assert d.tier == 1
    assert d.override_allowed is False

def test_tier1_booking_flow_critical():
    results = [make_ab("book1", "booking_flow", -0.20, 3.0)]
    results += [make_ab(f"t{i}", "flight_search", 0.1, 2.0) for i in range(4)]
    d = gate_check(results)
    assert d.verdict == "BLOCK"
    assert d.tier == 1

def test_tier2_soft_block():
    # weighted delta between -0.05 and 0
    results = [make_ab(f"t{i}", "flight_search", -0.02, 2.0) for i in range(3)]
    results += [make_ab(f"t{i+3}", "flight_search", 0.05, 2.0) for i in range(2)]
    d = gate_check(results)
    assert d.verdict in ("SOFT_BLOCK", "WARN", "BLOCK")

def test_tier3_warn():
    results = [make_ab("t1", "flight_search", -0.02, 1.0)]
    results += [make_ab(f"t{i+2}", "flight_search", 0.15, 1.0) for i in range(9)]
    d = gate_check(results)
    assert d.verdict in ("WARN", "PASS")

def test_regression_rate_block():
    # >30% regression triggers T1
    results = [make_ab(f"t{i}", "flight_search", -0.01, 1.0) for i in range(4)]
    results += [make_ab(f"t{i+4}", "flight_search", 0.1, 1.0) for i in range(6)]
    # 4/10 = 40% regression
    d = gate_check(results)
    assert d.verdict == "BLOCK"
```

- [ ] **Step 2: Run — expect ImportError**

```bash
pytest tests/test_gate_check.py -v
```

- [ ] **Step 3: Write eval/gate_thresholds.yaml**

```yaml
# eval/gate_thresholds.yaml
tier1:
  weighted_delta_min: -0.05
  critical_task_delta_min: -0.15
  regression_rate_max: 0.30

tier2:
  weighted_delta_min: 0.0
  heavy_task_delta_min: -0.10
  regression_rate_max: 0.20

tier3:
  small_regression_delta_min: -0.05

calibration_log:
  - date: "2026-06-03"
    false_positive_rate: null
    false_negative_rate: null
    changes: "initial thresholds"
```

- [ ] **Step 4: Write eval/gate_check.py**

```python
# eval/gate_check.py
from __future__ import annotations
import argparse
import json
import pathlib
import sys
import yaml
from eval.schemas import ABResult, GateDecision

TASK_WEIGHTS = {
    "booking_flow": 3.0,
    "flight_search": 2.0,
    "hotel_search": 2.0,
    "itinerary_build": 1.5,
    "fare_rules": 1.0,
    "edge_cases": 0.5,
}

def load_thresholds(path: str = "eval/gate_thresholds.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def compute_weighted_delta(results: list[ABResult], weights: dict[str, float]) -> float:
    total_weight = sum(weights.get(r.domain, 1.0) for r in results)
    if total_weight == 0:
        return 0.0
    return sum(r.delta * weights.get(r.domain, 1.0) for r in results) / total_weight


def gate_check(
    results: list[ABResult],
    thresholds_path: str = "eval/gate_thresholds.yaml",
    langsmith_url: str = "",
) -> GateDecision:
    t = load_thresholds(thresholds_path)
    t1, t2, t3 = t["tier1"], t["tier2"], t["tier3"]

    weighted_delta = compute_weighted_delta(results, TASK_WEIGHTS)
    regression_rate = sum(1 for r in results if r.delta < 0) / len(results) if results else 0.0

    critical = [
        r for r in results
        if TASK_WEIGHTS.get(r.domain, 1.0) >= 3.0 and r.delta < t1["critical_task_delta_min"]
    ]
    heavy_regressions = [
        r for r in results
        if TASK_WEIGHTS.get(r.domain, 1.0) >= 2.0 and r.delta < t2["heavy_task_delta_min"]
    ]

    # Tier 1 — hard block
    if critical or weighted_delta < t1["weighted_delta_min"] or regression_rate > t1["regression_rate_max"]:
        return GateDecision(
            verdict="BLOCK", tier=1,
            weighted_delta=weighted_delta,
            regression_rate=regression_rate,
            flagged_tasks=[r.task_id for r in critical],
            langsmith_experiment_url=langsmith_url,
            override_allowed=False,
        )

    # Tier 2 — soft block
    if heavy_regressions or weighted_delta < t2["weighted_delta_min"] or regression_rate > t2["regression_rate_max"]:
        return GateDecision(
            verdict="SOFT_BLOCK", tier=2,
            weighted_delta=weighted_delta,
            regression_rate=regression_rate,
            flagged_tasks=[r.task_id for r in heavy_regressions],
            langsmith_experiment_url=langsmith_url,
            override_allowed=True,
        )

    # Tier 3 — warn
    small_regressions = [r for r in results if t3["small_regression_delta_min"] < r.delta < 0]
    if small_regressions:
        return GateDecision(
            verdict="WARN", tier=3,
            weighted_delta=weighted_delta,
            regression_rate=regression_rate,
            flagged_tasks=[r.task_id for r in small_regressions],
            langsmith_experiment_url=langsmith_url,
            override_allowed=True,
        )

    return GateDecision(
        verdict="PASS", tier=0,
        weighted_delta=weighted_delta,
        regression_rate=regression_rate,
        flagged_tasks=[],
        langsmith_experiment_url=langsmith_url,
        override_allowed=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="ab_results.json")
    args = parser.parse_args()

    raw = json.loads(pathlib.Path(args.results).read_text())
    # Reconstruct ABResult objects from JSON
    results = []
    for r in raw:
        no_s = r["no_skill"]
        with_s = r["with_skill"]
        from eval.schemas import EvalResult
        no_eval = EvalResult(**no_s)
        with_eval = EvalResult(**with_s)
        ab = ABResult.from_pair(r["skill_name"], no_eval, with_eval, r["task_weight"])
        results.append(ab)

    decision = gate_check(results)

    icon = {"PASS": "✓", "WARN": "⚠", "SOFT_BLOCK": "✗", "BLOCK": "✗✗"}[decision.verdict]
    print(f"\nGate Decision: {icon} {decision.verdict} (Tier {decision.tier})")
    print(f"  Weighted delta:  {decision.weighted_delta:+.3f}")
    print(f"  Regression rate: {decision.regression_rate:.0%}")
    if decision.flagged_tasks:
        print(f"  Flagged tasks:   {', '.join(decision.flagged_tasks)}")

    if decision.tier in (1, 2):
        sys.exit(1)
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
pytest tests/test_gate_check.py -v
```

- [ ] **Step 6: Write eval/ab_compare.py**

```python
# eval/ab_compare.py
"""Async A/B harness: runs no_skill vs with_skill for all tasks in a domain."""
from __future__ import annotations
import argparse
import asyncio
import dataclasses
import json
import pathlib
import os
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from eval.run_task import run_task
from eval.schemas import ABResult
from eval.gate_check import gate_check, TASK_WEIGHTS

N_TRIALS = int(os.environ.get("EVAL_TRIALS", "5"))


def load_tasks_for_skill(skill_name: str) -> list[pathlib.Path]:
    tasks_dir = pathlib.Path("tasks")
    matched = []
    for task_dir in sorted(tasks_dir.iterdir()):
        toml_path = task_dir / "task.toml"
        if not toml_path.exists():
            continue
        with open(toml_path, "rb") as f:
            meta = tomllib.load(f)
        if meta["task"].get("skill") == skill_name:
            matched.append(task_dir)
    return matched


async def run_ab_for_task(
    task_path: pathlib.Path,
    skill_path: pathlib.Path,
    n_trials: int,
) -> ABResult:
    loop = asyncio.get_event_loop()

    no_skill_scores = []
    with_skill_scores = []

    for _ in range(n_trials):
        r_no = await loop.run_in_executor(None, run_task, str(task_path), None, "no_skill")
        r_with = await loop.run_in_executor(None, run_task, str(task_path), str(skill_path), "with_skill")
        no_skill_scores.append(r_no)
        with_skill_scores.append(r_with)

    import statistics
    best_no = max(no_skill_scores, key=lambda r: r.score)
    best_with = max(with_skill_scores, key=lambda r: r.score)

    with open(task_path / "task.toml", "rb") as f:
        meta = tomllib.load(f)
    domain = meta["task"]["domain"]
    weight = TASK_WEIGHTS.get(domain, 1.0)

    return ABResult.from_pair(
        skill_name=skill_path.name,
        no_skill=best_no,
        with_skill=best_with,
        task_weight=weight,
    )


async def run_ab_compare(skill_name: str, skill_path: pathlib.Path, n_trials: int) -> list[ABResult]:
    tasks = load_tasks_for_skill(skill_name)
    if not tasks:
        print(f"No tasks found for skill '{skill_name}'")
        return []

    coros = [run_ab_for_task(t, skill_path, n_trials) for t in tasks]
    return await asyncio.gather(*coros)


def print_report(results: list[ABResult], decision):
    print(f"\nA/B Evaluation: {results[0].skill_name if results else '?'}  (N={N_TRIALS} trials)")
    print("─" * 70)
    print(f"{'task':<30} {'weight':>6}  {'no_skill':>8}  {'with_skill':>10}  {'Δ':>7}  flag")
    for r in sorted(results, key=lambda x: x.task_id):
        flag = "⚠ REGRESSION" if r.regression else ("✓" if r.delta > 0.05 else "–")
        print(f"{r.task_id:<30} {r.task_weight:>6.1f}  {r.no_skill.score:>8.2f}  {r.with_skill.score:>10.2f}  {r.delta:>+7.2f}  {flag}")
    print("─" * 70)
    print(f"Weighted delta: {decision.weighted_delta:+.3f}    Regression rate: {decision.regression_rate:.0%}")
    icon = {"PASS": "✓ PASS", "WARN": "⚠ WARN", "SOFT_BLOCK": "✗ SOFT BLOCK", "BLOCK": "✗✗ BLOCK"}
    print(f"GATE VERDICT:  {icon[decision.verdict]} (Tier {decision.tier})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True, help="e.g. concrete/flight-search")
    parser.add_argument("--trials", type=int, default=N_TRIALS)
    parser.add_argument("--output", default="ab_results.json")
    args = parser.parse_args()

    skill_path = pathlib.Path("skills") / args.skill
    skill_name = skill_path.name

    results = asyncio.run(run_ab_compare(skill_name, skill_path, args.trials))
    decision = gate_check(results)
    print_report(results, decision)

    serialized = [
        {**dataclasses.asdict(r), "no_skill": dataclasses.asdict(r.no_skill),
         "with_skill": dataclasses.asdict(r.with_skill)}
        for r in results
    ]
    pathlib.Path(args.output).write_text(json.dumps(serialized, indent=2))
    print(f"\nResults written to {args.output}")

    if decision.tier in (1, 2):
        sys.exit(1)
```

- [ ] **Step 7: Run gate tests again to confirm still passing**

```bash
pytest tests/test_gate_check.py -v
```

- [ ] **Step 8: Commit**

```bash
git add eval/ab_compare.py eval/gate_check.py eval/gate_thresholds.yaml tests/test_gate_check.py
git commit -m "feat: A/B harness with tiered gate logic"
```

---

### Task 8: Skill Coverage P/R

**Files:**
- Modify: `eval/ab_compare.py` (add `compute_coverage_metrics` function)
- Create: `eval/coverage.py`

- [ ] **Step 1: Write eval/coverage.py**

```python
# eval/coverage.py
"""Compute skill coverage precision/recall from A/B results."""
from __future__ import annotations
from eval.schemas import ABResult, SkillCoverageMetrics

TRIGGER_TARGETS = {"precision": 0.85, "recall": 0.80, "no_trigger_precision": 0.90}


def compute_coverage_metrics(
    skill_name: str,
    results: list[ABResult],
    trigger_precision: float,
    trigger_recall: float,
    no_trigger_precision: float,
) -> SkillCoverageMetrics:
    """
    Coverage P/R is derived from A/B results:
      precision = tasks where skill triggered AND delta > 0 / tasks where skill triggered
      recall    = tasks where skill triggered AND delta > 0 / total relevant tasks (all in domain)
    """
    triggered_and_helped = sum(1 for r in results if r.delta > 0)
    triggered = len(results)
    relevant = triggered  # all tasks in the domain are "relevant" for the skill

    coverage_precision = triggered_and_helped / triggered if triggered > 0 else 0.0
    coverage_recall = triggered_and_helped / relevant if relevant > 0 else 0.0

    strategy = _select_strategy(coverage_precision, coverage_recall, trigger_precision, trigger_recall)

    return SkillCoverageMetrics(
        skill_name=skill_name,
        trigger_precision=trigger_precision,
        trigger_recall=trigger_recall,
        no_trigger_precision=no_trigger_precision,
        coverage_precision=coverage_precision,
        coverage_recall=coverage_recall,
        optimizer_strategy=strategy,
    )


def _select_strategy(cov_p: float, cov_r: float, trig_p: float, trig_r: float) -> str:
    if trig_p < 0.75:
        return "variant_1_tighten_triggers"
    if trig_r < 0.75:
        return "variant_2_broaden_triggers"
    if cov_p > 0.85 and cov_r > 0.80:
        return "variant_3_edge_case_handling"
    return "variant_4_focused_modules"


def print_coverage_report(metrics: SkillCoverageMetrics):
    print("\nSkill Coverage P/R:")
    print(f"  Trigger precision:   {metrics.trigger_precision:.2f}  {'✓' if metrics.trigger_precision >= TRIGGER_TARGETS['precision'] else '← below target'}")
    print(f"  Trigger recall:      {metrics.trigger_recall:.2f}  {'✓' if metrics.trigger_recall >= TRIGGER_TARGETS['recall'] else '← below target'}")
    print(f"  Coverage precision:  {metrics.coverage_precision:.2f}")
    print(f"  Coverage recall:     {metrics.coverage_recall:.2f}")
    print(f"  Optimizer strategy:  {metrics.optimizer_strategy}")
```

- [ ] **Step 2: Commit**

```bash
git add eval/coverage.py
git commit -m "feat: skill coverage precision/recall computation"
```

---

### Task 9: Trigger Router Eval

**Files:**
- Create: `trigger/labeled_requests.json`
- Create: `eval/trigger_eval.py`

- [ ] **Step 1: Write trigger/labeled_requests.json**

```json
[
  {"id": "tr01", "request": "Find flights from New York to LA next Friday", "expected_skill": "flight-search"},
  {"id": "tr02", "request": "Search for hotels in Miami for next weekend", "expected_skill": "hotel-search"},
  {"id": "tr03", "request": "Book a flight to Chicago for Alice Johnson", "expected_skill": "book-itinerary"},
  {"id": "tr04", "request": "What are the cancellation rules for my flight?", "expected_skill": "fare-rules"},
  {"id": "tr05", "request": "Plan a 3-day trip to New Orleans with flights and hotel", "expected_skill": "book-itinerary"},
  {"id": "tr06", "request": "I need a roundtrip to Seattle from Boston in August", "expected_skill": "flight-search"},
  {"id": "tr07", "request": "Find a 4-star hotel near the airport in Dallas", "expected_skill": "hotel-search"},
  {"id": "tr08", "request": "Can I change my flight date? What does it cost?", "expected_skill": "fare-rules"},
  {"id": "tr09", "request": "Book me into the Marriott in Chicago for two nights", "expected_skill": "book-itinerary"},
  {"id": "tr10", "request": "What flights go from SFO to JFK tomorrow morning?", "expected_skill": "flight-search"},
  {"id": "tr11", "request": "Is my booking refundable?", "expected_skill": "fare-rules"},
  {"id": "tr12", "request": "Find cheap hotels downtown Seattle in October", "expected_skill": "hotel-search"},
  {"id": "tr13", "request": "I want to fly to Denver on July 4th weekend", "expected_skill": "flight-search"},
  {"id": "tr14", "request": "Complete my itinerary for the LA trip", "expected_skill": "book-itinerary"},
  {"id": "tr15", "request": "Search one-way flights ORD to MIA Sept 10", "expected_skill": "flight-search"},
  {"id": "tr16", "request": "What hotels are available in Nashville August 15-18?", "expected_skill": "hotel-search"},
  {"id": "tr17", "request": "I need a business class seat to London from JFK", "expected_skill": "flight-search"},
  {"id": "tr18", "request": "Book the Hilton Garden Inn for my conference trip", "expected_skill": "book-itinerary"},
  {"id": "tr19", "request": "Tell me the baggage allowance for my ticket", "expected_skill": "fare-rules"},
  {"id": "tr20", "request": "Are there any budget flights from PHX to SEA next month?", "expected_skill": "flight-search"},
  {"id": "tr21", "request": "Reserve a hotel near Disneyland for 3 nights", "expected_skill": "hotel-search"},
  {"id": "tr22", "request": "How much is it to cancel my current reservation?", "expected_skill": "fare-rules"},
  {"id": "tr23", "request": "What is the weather in Paris next week?", "expected_skill": null},
  {"id": "tr24", "request": "Tell me a joke about airports", "expected_skill": null},
  {"id": "tr25", "request": "What is the capital of France?", "expected_skill": null},
  {"id": "tr26", "request": "What time is it in Tokyo?", "expected_skill": null},
  {"id": "tr27", "request": "Can you translate 'hello' to Spanish?", "expected_skill": null},
  {"id": "tr28", "request": "Who won the World Cup in 2022?", "expected_skill": null},
  {"id": "tr29", "request": "I need a flight and want to know if hotels are expensive there", "expected_skill": "flight-search"},
  {"id": "tr30", "request": "Check if my passport is valid for international travel", "expected_skill": null}
]
```

- [ ] **Step 2: Write eval/trigger_eval.py**

```python
# eval/trigger_eval.py
"""Evaluate trigger routing accuracy per skill on labeled_requests.json."""
from __future__ import annotations
import argparse
import json
import os
import pathlib
from collections import defaultdict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

SKILLS = ["flight-search", "hotel-search", "book-itinerary", "fare-rules"]

ROUTER_PROMPT = """You are a travel agent skill router. Given a user request, decide which skill (if any) should handle it.

Available skills:
- flight-search: searching for flights, finding available departures, comparing airfares
- hotel-search: finding hotels, checking hotel availability, comparing accommodation
- book-itinerary: completing bookings, creating reservations, planning full trips
- fare-rules: cancellation policies, change fees, baggage rules, refund conditions

Respond with ONLY a JSON object:
{{"skill": "<skill-name-or-null>", "confidence": <0.0-1.0>}}

If no skill is relevant, use null for skill."""


def route_request(request: str, llm) -> str | None:
    msg = llm.invoke([
        SystemMessage(content=ROUTER_PROMPT),
        HumanMessage(content=request),
    ])
    try:
        data = json.loads(msg.content)
        return data.get("skill")
    except (json.JSONDecodeError, AttributeError):
        return None


def compute_pr(labeled: list[dict], predictions: list[str | None], skill: str) -> dict:
    tp = sum(1 for l, p in zip(labeled, predictions) if l["expected_skill"] == skill and p == skill)
    fp = sum(1 for l, p in zip(labeled, predictions) if l["expected_skill"] != skill and p == skill)
    fn = sum(1 for l, p in zip(labeled, predictions) if l["expected_skill"] == skill and p != skill)
    tn = sum(1 for l, p in zip(labeled, predictions) if l["expected_skill"] != skill and p != skill)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    no_trigger_precision = tn / (tn + fn) if (tn + fn) > 0 else 0.0
    return {"precision": precision, "recall": recall, "no_trigger_precision": no_trigger_precision,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labeled", default="trigger/labeled_requests.json")
    parser.add_argument("--output", default="trigger_eval_results.json")
    args = parser.parse_args()

    labeled = json.loads(pathlib.Path(args.labeled).read_text())
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", api_key=os.environ["ANTHROPIC_API_KEY"])

    predictions = [route_request(item["request"], llm) for item in labeled]

    print("\nTrigger Evaluation")
    print("─" * 60)
    print(f"{'Skill':<20} {'Precision':>9}  {'Recall':>6}  {'No-trig P':>9}")

    all_metrics = {}
    for skill in SKILLS:
        m = compute_pr(labeled, predictions, skill)
        all_metrics[skill] = m
        p_flag = "✓" if m["precision"] >= 0.85 else "← below"
        r_flag = "✓" if m["recall"] >= 0.80 else "← below"
        print(f"{skill:<20} {m['precision']:>9.2f}{p_flag:>6}  {m['recall']:>6.2f}{r_flag:>6}")

    pathlib.Path(args.output).write_text(json.dumps(all_metrics, indent=2))
    print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add trigger/ eval/trigger_eval.py
git commit -m "feat: trigger router eval with P/R per skill"
```

---

### Task 10: Pseudo-GRPO Optimizer

**Files:**
- Create: `eval/optimizer/variant_strategies.py`
- Create: `eval/optimizer/optimizer.py`
- Create: `eval/optimizer/__init__.py`

- [ ] **Step 1: Write eval/optimizer/variant_strategies.py**

```python
# eval/optimizer/variant_strategies.py

STRATEGIES = {
    "variant_1_tighten_triggers": """
Rewrite the "When to Use" section of this skill to be more specific and restrictive.
The current skill is triggering on requests it shouldn't handle (low precision).
Add 2-3 explicit "Do NOT use when:" conditions. Keep the workflow section unchanged.
""",
    "variant_2_broaden_triggers": """
Expand the "When to Use" section to cover more related request patterns.
The skill is missing relevant requests (low recall).
Add 3-4 additional trigger examples. Look at the failing tasks for patterns.
""",
    "variant_3_edge_case_handling": """
Add an "Edge Cases" section to the skill documenting the specific failure patterns
from the failing traces. Add explicit handling steps for each edge case.
Keep trigger conditions unchanged.
""",
    "variant_4_focused_modules": """
Reduce this skill to its 2-3 most essential modules only.
Cut any step not directly required for the core use case.
SkillsBench shows focused 2-3 module skills outperform comprehensive ones.
""",
    "variant_5_restructure_workflow": """
Reorder the Workflow section based on what the failing traces show the agent
actually needs to do first. Move the most commonly needed step to position 1.
Do not change the content of any step, only the order.
""",
}


def get_strategy_prompt(strategy_key: str, skill_content: str, failing_traces: list[str]) -> str:
    base = STRATEGIES.get(strategy_key, STRATEGIES["variant_4_focused_modules"])
    traces_summary = "\n".join(f"- {t}" for t in failing_traces[:5])
    return f"""You are improving a travel agent skill document.

Current SKILL.md:
{skill_content}

Failing task summaries:
{traces_summary}

Instruction:
{base}

Output ONLY the improved SKILL.md content. No explanations, no markdown fences."""
```

- [ ] **Step 2: Write eval/optimizer/optimizer.py**

```python
# eval/optimizer/optimizer.py
"""Pseudo-GRPO skill optimizer: generate K variants, score, select, iterate."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import pathlib
import sys

import anthropic

from eval.optimizer.variant_strategies import STRATEGIES, get_strategy_prompt
from eval.run_task import run_task
from eval.gate_check import TASK_WEIGHTS
from eval.schemas import ABResult

K = 5          # variants per round
MAX_ROUNDS = 5
THRESHOLD = 0.03
FAST_EVAL_TASKS = 8


def generate_variant(
    skill_content: str,
    failing_traces: list[str],
    strategy_key: str,
    client: anthropic.Anthropic,
) -> str:
    prompt = get_strategy_prompt(strategy_key, skill_content, failing_traces)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def score_skill_content(
    skill_content: str,
    task_paths: list[pathlib.Path],
    skill_name: str,
    tmp_path: pathlib.Path,
) -> float:
    tmp_skill = tmp_path / "SKILL.md"
    tmp_skill.write_text(skill_content)

    scores = []
    for task_path in task_paths[:FAST_EVAL_TASKS]:
        try:
            r = run_task(str(task_path), str(tmp_path), "with_skill")
            scores.append(r.score)
        except Exception:
            scores.append(0.0)

    return sum(scores) / len(scores) if scores else 0.0


def get_failing_tasks(skill_name: str, ab_results_path: str) -> list[pathlib.Path]:
    if not pathlib.Path(ab_results_path).exists():
        return list(pathlib.Path("tasks").iterdir())[:FAST_EVAL_TASKS]

    raw = json.loads(pathlib.Path(ab_results_path).read_text())
    failing_ids = {r["task_id"] for r in raw if r["delta"] < 0}
    all_tasks = list(pathlib.Path("tasks").iterdir())
    failing = [t for t in all_tasks if t.name in failing_ids]
    return failing[:FAST_EVAL_TASKS] if failing else all_tasks[:FAST_EVAL_TASKS]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True, help="e.g. concrete/fare-rules")
    parser.add_argument("--strategy", default=None,
                        help="Initial strategy key; auto-selected from coverage metrics if omitted")
    parser.add_argument("--ab-results", default="ab_results.json")
    parser.add_argument("--output-dir", default="eval/optimizer_output")
    args = parser.parse_args()

    skill_path = pathlib.Path("skills") / args.skill
    skill_name = skill_path.name
    skill_content = (skill_path / "SKILL.md").read_text()

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = output_dir / "_tmp_variant"
    tmp_dir.mkdir(exist_ok=True)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tasks = get_failing_tasks(skill_name, args.ab_results)
    failing_traces = [
        f"Task {t.name}: {(t / 'instruction.md').read_text().strip()[:100]}"
        for t in tasks
    ]

    strategy_keys = list(STRATEGIES.keys())
    baseline_score = score_skill_content(skill_content, tasks, skill_name, tmp_dir)
    print(f"\nOptimizer: {skill_name}")
    print(f"Baseline fast-eval score: {baseline_score:.2f}")

    current_best_content = skill_content
    current_best_score = baseline_score

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\nRound {round_num}: generating {K} variants...")
        variants = []
        for i, strategy_key in enumerate(strategy_keys[:K]):
            variant = generate_variant(current_best_content, failing_traces, strategy_key, client)
            score = score_skill_content(variant, tasks, skill_name, tmp_dir)
            delta = score - baseline_score
            marker = " <- BEST" if score == max(score, current_best_score) else ""
            print(f"  {strategy_key:<35} {score:.2f}  {delta:+.2f}{marker}")
            variants.append((score, variant, strategy_key))

        variants.sort(key=lambda x: x[0], reverse=True)
        top_score, top_content, top_strategy = variants[0]

        if top_score > current_best_score + THRESHOLD:
            current_best_score = top_score
            current_best_content = top_content
        else:
            print(f"Converged after {round_num} rounds.")
            break

    version_tag = f"{skill_name}_proposed"
    output_file = output_dir / f"{version_tag}.md"
    output_file.write_text(current_best_content)

    print(f"\nProposed: {output_file} (score: {current_best_score:.2f} vs baseline {baseline_score:.2f})")
    print(f"Run full eval: python eval/ab_compare.py --skill {args.skill}")
    print("NOTE: Human review required before committing any proposed skill.")


if __name__ == "__main__":
    main()
```

```python
# eval/optimizer/__init__.py
```

- [ ] **Step 3: Commit**

```bash
git add eval/optimizer/
git commit -m "feat: pseudo-GRPO skill optimizer (propose only, never auto-commits)"
```

---

### Task 11: SkillPyramid Analyzer

**Files:**
- Create: `pyramid/analyze.py`
- Create: `skills/concrete/flight-search/SKILL.md` (seed skill)
- Create: `skills/concrete/hotel-search/SKILL.md`
- Create: `skills/concrete/fare-rules/SKILL.md`
- Create: `skills/abstract/book-itinerary/SKILL.md`

- [ ] **Step 1: Write seed skills**

```bash
mkdir -p skills/{atomic,concrete/{flight-search,hotel-search,fare-rules},abstract/book-itinerary}
```

```markdown
<!-- skills/concrete/flight-search/SKILL.md -->
# flight-search

## When to Use
When the user asks to find, search, or compare flights between two destinations.

## Workflow
1. Extract origin, destination, and travel date from user message
2. Call search_flights with extracted parameters
3. Present top 3 results sorted by price
4. Ask user if they want to book one

## When NOT to Use
- User is asking about hotel accommodations only
- User is asking about fare cancellation policies (use fare-rules instead)
```

```markdown
<!-- skills/concrete/hotel-search/SKILL.md -->
# hotel-search

## When to Use
When the user asks to find, search, or compare hotel accommodations.

## Workflow
1. Extract location, check-in, check-out dates from user message
2. Call search_hotels with extracted parameters
3. Present top 3 results sorted by price per night
4. Ask user if they want to book one

## When NOT to Use
- User is asking about flights only
- User already has a hotel and wants to modify it (use modify-booking)
```

```markdown
<!-- skills/concrete/fare-rules/SKILL.md -->
# fare-rules

## When to Use
When user asks about cancellation policies, change fees, refunds, or baggage rules for a flight.

## Workflow
1. Identify the flight_id from context or ask the user
2. Call get_fare_rules with the flight_id
3. Summarize cancellation, change, and baggage rules in plain language

## When NOT to Use
- User wants to search for new flights
- User wants to book or modify a booking
```

```markdown
<!-- skills/abstract/book-itinerary/SKILL.md -->
# book-itinerary

## When to Use
When user wants to complete a full booking (flight + hotel) or plan a multi-step trip itinerary.

[reuse skill: flight-search | when: user needs flights as part of itinerary | provides: flight options]
[reuse skill: hotel-search | when: user needs hotels as part of itinerary | provides: hotel options]

## Workflow
1. Determine what components the trip needs (flight, hotel, or both)
2. Execute flight-search workflow if flights needed
3. Execute hotel-search workflow if hotels needed
4. Validate passenger details via validate_passenger
5. Call create_booking for each confirmed component
6. Present full itinerary summary

## When NOT to Use
- User only wants to search without booking
```

- [ ] **Step 2: Write pyramid/analyze.py**

```python
# pyramid/analyze.py
"""Analyze skill library and suggest atomic extractions + abstract inductions."""
from __future__ import annotations
import argparse
import json
import os
import pathlib

import anthropic

ANALYZE_PROMPT = """You are analyzing a travel agent skill library.

Here are all current skills with their content:
{skills_block}

Tasks:
1. Identify operations that appear in 3 or more skills and could be extracted as atomic skills.
   For each: give a suggested name, what it does, and which skills currently inline it.

2. Identify 2-3 skills that share a high-level task schema and could be grouped under an abstract skill.
   For each: give a suggested abstract skill name and which concrete skills it would compose.

Respond as JSON:
{{
  "atomic_extractions": [
    {{"name": "parse-date-range", "description": "...", "used_by": ["skill-a", "skill-b"]}}
  ],
  "abstract_inductions": [
    {{"name": "book-itinerary", "description": "...", "composes": ["flight-search", "hotel-search"]}}
  ]
}}"""


def load_all_skills(skills_dir: pathlib.Path) -> dict[str, str]:
    skills = {}
    for layer in ["atomic", "concrete", "abstract"]:
        layer_dir = skills_dir / layer
        if not layer_dir.exists():
            continue
        for skill_dir in layer_dir.iterdir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skills[f"{layer}/{skill_dir.name}"] = skill_file.read_text()
    return skills


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-dir", default="skills")
    parser.add_argument("--output", default="pyramid_suggestions.json")
    args = parser.parse_args()

    skills = load_all_skills(pathlib.Path(args.skills_dir))
    if not skills:
        print("No skills found.")
        return

    skills_block = "\n\n".join(f"### {name}\n{content}" for name, content in skills.items())
    prompt = ANALYZE_PROMPT.format(skills_block=skills_block)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text
    try:
        suggestions = json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        suggestions = json.loads(match.group()) if match else {"raw": raw}

    pathlib.Path(args.output).write_text(json.dumps(suggestions, indent=2))
    print(f"Suggestions written to {args.output}")

    if "atomic_extractions" in suggestions:
        print(f"\nAtomic extraction candidates ({len(suggestions['atomic_extractions'])}):")
        for a in suggestions["atomic_extractions"]:
            print(f"  - {a['name']}: {a['description'][:80]}")

    if "abstract_inductions" in suggestions:
        print(f"\nAbstract induction candidates ({len(suggestions['abstract_inductions'])}):")
        for a in suggestions["abstract_inductions"]:
            print(f"  - {a['name']} composes: {', '.join(a['composes'])}")

    print("\nReview pyramid_suggestions.json before applying any changes.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add skills/ pyramid/
git commit -m "feat: seed skills and SkillPyramid analyzer"
```

---

### Task 12: Leaderboard

**Files:**
- Create: `eval/leaderboard.py`

- [ ] **Step 1: Write eval/leaderboard.py**

```python
# eval/leaderboard.py
"""Aggregate all ab_results.json files into a skill leaderboard."""
from __future__ import annotations
import argparse
import json
import pathlib
from collections import defaultdict
from datetime import datetime

def collect_results(results_dir: pathlib.Path) -> dict[str, list[dict]]:
    """Collect all ab_results.json files, keyed by skill name."""
    by_skill = defaultdict(list)
    for path in sorted(results_dir.rglob("ab_results*.json")):
        try:
            data = json.loads(path.read_text())
            for r in data:
                by_skill[r["skill_name"]].append(r)
        except (json.JSONDecodeError, KeyError):
            continue
    return dict(by_skill)


def summarize_skill(skill_name: str, results: list[dict]) -> dict:
    if not results:
        return {}
    total_w = sum(r.get("task_weight", 1.0) for r in results)
    weighted_delta = sum(r["delta"] * r.get("task_weight", 1.0) for r in results) / total_w if total_w else 0
    regression_rate = sum(1 for r in results if r["delta"] < 0) / len(results)
    return {
        "skill": skill_name,
        "weighted_delta": round(weighted_delta, 3),
        "regression_rate": round(regression_rate, 2),
        "n_tasks": len(results),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default=".")
    args = parser.parse_args()

    by_skill = collect_results(pathlib.Path(args.results_dir))
    if not by_skill:
        print("No ab_results.json files found.")
        return

    summaries = [summarize_skill(k, v) for k, v in by_skill.items()]
    summaries.sort(key=lambda x: x["weighted_delta"], reverse=True)

    print(f"\nSkill Leaderboard — {datetime.now().strftime('%Y-%m-%d')}")
    print("─" * 65)
    print(f"{'Skill':<25} {'Δ (weighted)':>12}  {'Regr rate':>9}  {'N tasks':>7}")
    for s in summaries:
        flag = "← needs optimizer" if s["weighted_delta"] < 0.05 else ""
        print(f"{s['skill']:<25} {s['weighted_delta']:>+12.3f}  {s['regression_rate']:>9.0%}  {s['n_tasks']:>7}  {flag}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add eval/leaderboard.py
git commit -m "feat: skill leaderboard aggregator"
```

---

### Task 13: GitHub CI Gate

**Files:**
- Create: `.github/workflows/eval_skill.yml`
- Create: `.github/scripts/detect_skill.py`
- Create: `eval/security/approved_tools.json`

- [ ] **Step 1: Write .github/scripts/detect_skill.py**

```python
#!/usr/bin/env python3
# .github/scripts/detect_skill.py
"""Detect which skill was changed in this PR and print its path."""
import subprocess
import pathlib
import sys

result = subprocess.run(
    ["git", "diff", "--name-only", "HEAD^1", "HEAD"],
    capture_output=True, text=True,
)
changed = result.stdout.strip().split("\n")
for path in changed:
    p = pathlib.Path(path)
    if "skills/" in path and "SKILL.md" in path:
        # Return the skill directory (parent of SKILL.md)
        print(str(p.parent))
        sys.exit(0)

print("")  # no skill changed
sys.exit(0)
```

- [ ] **Step 2: Write eval/security/approved_tools.json**

```json
{
  "approved_mcp_tools": [
    "search_flights", "search_hotels", "check_availability",
    "get_fare_rules", "validate_passenger", "create_booking",
    "modify_booking", "cancel_booking", "get_itinerary"
  ],
  "approved_external_domains": ["mcp.mondee.com"]
}
```

- [ ] **Step 3: Write .github/workflows/eval_skill.yml**

```yaml
name: Skill Eval Gate

on:
  pull_request:
    paths:
      - 'skills/**'

jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Detect changed skill
        id: skill
        run: echo "skill=$(python .github/scripts/detect_skill.py)" >> $GITHUB_OUTPUT

      - name: Validate skill format
        if: steps.skill.outputs.skill != ''
        run: |
          SKILL="${{ steps.skill.outputs.skill }}"
          python -c "
          import pathlib, sys
          skill_file = pathlib.Path('$SKILL') / 'SKILL.md'
          if not skill_file.exists():
              print(f'ERROR: {skill_file} not found')
              sys.exit(1)
          content = skill_file.read_text()
          required = ['# ', '## When to Use', '## Workflow']
          missing = [r for r in required if r not in content]
          if missing:
              print(f'SKILL.md missing sections: {missing}')
              sys.exit(1)
          print('Skill format valid')
          "

      - name: Check MCP tool scope
        if: steps.skill.outputs.skill != ''
        run: |
          python -c "
          import json, pathlib, re, sys
          approved = json.loads(pathlib.Path('eval/security/approved_tools.json').read_text())
          skill_content = (pathlib.Path('${{ steps.skill.outputs.skill }}') / 'SKILL.md').read_text()
          tool_refs = re.findall(r'\b(search_\w+|check_\w+|get_\w+|create_\w+|modify_\w+|cancel_\w+|validate_\w+)\b', skill_content)
          unapproved = [t for t in tool_refs if t not in approved['approved_mcp_tools'] + ['search_flights','search_hotels']]
          if unapproved:
              print(f'Unapproved MCP tool references: {unapproved}')
              sys.exit(1)
          print('MCP scope check passed')
          "

  eval:
    needs: security-scan
    runs-on: ubuntu-latest
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_API_KEY }}
      LANGCHAIN_TRACING_V2: "true"
      LANGSMITH_PROJECT: "skill-testing-playground"

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Detect changed skill
        id: skill
        run: echo "skill=$(python .github/scripts/detect_skill.py)" >> $GITHUB_OUTPUT

      - name: Skip if no skill changed
        if: steps.skill.outputs.skill == ''
        run: echo "No skill changed, skipping eval" && exit 0

      - name: Start mock MCP server
        run: |
          python eval/mock_mcp/server.py &
          sleep 2

      - name: Run A/B eval
        run: |
          SKILL_LAYER=$(echo "${{ steps.skill.outputs.skill }}" | cut -d'/' -f1)
          SKILL_NAME=$(echo "${{ steps.skill.outputs.skill }}" | cut -d'/' -f2)
          python eval/ab_compare.py \
            --skill "${SKILL_LAYER}/${SKILL_NAME}" \
            --trials 5 \
            --output ab_results.json

      - name: Gate check
        id: gate
        run: |
          python eval/gate_check.py --results ab_results.json
          echo "exit_code=$?" >> $GITHUB_OUTPUT
        continue-on-error: true

      - name: Post PR comment
        if: always() && steps.skill.outputs.skill != ''
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            let body = '## Skill Eval Results\n\n';
            try {
              const results = JSON.parse(fs.readFileSync('ab_results.json', 'utf8'));
              const weighted = results.reduce((sum, r) => sum + r.delta * r.task_weight, 0) /
                               results.reduce((sum, r) => sum + r.task_weight, 0);
              const regressions = results.filter(r => r.delta < 0);
              const verdict = '${{ steps.gate.outputs.exit_code }}' === '0' ? '✓ PASS' : '✗ BLOCK/SOFT_BLOCK';

              body += `| Metric | Value |\n|--------|-------|\n`;
              body += `| Weighted delta | ${weighted.toFixed(3)} |\n`;
              body += `| Regression rate | ${regressions.length}/${results.length} (${(regressions.length/results.length*100).toFixed(0)}%) |\n`;
              body += `| Verdict | ${verdict} |\n\n`;

              if (regressions.length > 0) {
                body += `**Regressed tasks:**\n`;
                regressions.forEach(r => { body += `- ${r.task_id} (delta ${r.delta.toFixed(3)})\n`; });
              }
            } catch(e) {
              body += `Could not parse results: ${e.message}`;
            }

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body
            });
```

- [ ] **Step 4: Commit**

```bash
git add .github/ eval/security/approved_tools.json
git commit -m "feat: GitHub Actions CI gate for skill PRs"
```

---

## Self-Review

### Spec Coverage

| PRD Section | Covered by Task |
|-------------|-----------------|
| A/B eval harness with weighted delta + regression rate | Task 7, 8 |
| Travel task bank (20 tasks, 5 domains, BenchFlow) | Task 5 |
| Tiered CI gate T1/T2/T3/Pass | Task 7 (gate_check.py) |
| Trigger eval precision ≥ 0.85, recall ≥ 0.80 | Task 9 |
| Skill coverage P/R | Task 8 (coverage.py) |
| LangSmith integration + OTel tracing | Task 6 (run_task.py) |
| GitHub Actions CI gate | Task 13 |
| Pseudo-GRPO optimizer | Task 10 |
| SkillPyramid restructure | Task 11 |
| Security scanner (MCP scope check) | Task 13 (inline in CI) |
| Leaderboard | Task 12 |
| gate_thresholds.yaml | Task 7 |
| Data schemas | Task 2 |
| Mock MCP server | Task 3 |

### Gaps fixed
- `ABResult.from_pair` uses `N >= 5` for `delta_significant` — simplified to `abs(delta) > 0.05` since trial count is external. Acceptable for MVP.
- Security scanner uses inline Python in CI (no Promptfoo dependency for Week 1); Promptfoo config is in the architecture but not wired in this plan. Add as Week 2 task.
- `trigger_eval.py` uses LLM-as-router to simulate routing; does not test actual LangGraph skill selection (requires full agent integration). This matches Day 5 scope in PRD.

### Type consistency check
- `EvalResult` fields used in `ABResult.from_pair`: `score`, `steps`, `tokens_used` — all defined in Task 2 schema ✓
- `gate_check()` expects `list[ABResult]` with `.delta`, `.domain`, `.task_id` — all defined ✓
- `run_task()` returns `EvalResult` — used in `ab_compare.py` ✓
- `SkillCoverageMetrics` fields match `coverage.py` output ✓
