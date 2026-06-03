#!/usr/bin/env python3
"""Generates all 20 BenchFlow task directories."""
import os
import pathlib

ROOT = pathlib.Path("tasks")

TASKS = [
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


ROOT.mkdir(exist_ok=True)

for row in TASKS:
    task_id, domain, skill, verifier, weight, instruction, req_tools, req_params = row
    task_dir = ROOT / task_id
    (task_dir / "environment" / "skills" / skill).mkdir(parents=True, exist_ok=True)
    (task_dir / "solution").mkdir(exist_ok=True)
    (task_dir / "tests").mkdir(exist_ok=True)

    (task_dir / "instruction.md").write_text(instruction + "\n")

    toml_content = TASK_TOML_TEMPLATE.format(
        task_id=task_id, domain=domain, skill=skill, verifier=verifier,
        weight=weight, tools=quote_list(req_tools),
        required_params=format_required_params(req_params),
    )
    (task_dir / "task.toml").write_text(toml_content)

    solve_sh = SOLVE_SH_TEMPLATE.format(task_id=task_id, tools=", ".join(req_tools))
    solve_path = task_dir / "solution" / "solve.sh"
    solve_path.write_text(solve_sh)
    os.chmod(solve_path, 0o755)

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
