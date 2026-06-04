#!/usr/bin/env python3
"""Adds 29 more tasks to the existing task bank (expanding from 21 to 50)."""
import os
import pathlib

ROOT = pathlib.Path("tasks")

NEW_TASKS = [
    # Flight search — 6 more
    ("flight-search-005", "flight_search", "flight-search", "tool_call_check", 2.0,
     "Find flights from DEN to ORD on 2026-09-15 for 3 passengers.",
     ["search_flights"], {"search_flights": ["origin", "destination", "date", "passengers"]}),
    ("flight-search-006", "flight_search", "flight-search", "tool_call_check", 2.0,
     "What are the earliest morning flights from LAX to JFK on 2026-07-04?",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),
    ("flight-search-007", "flight_search", "flight-search", "tool_call_check", 2.0,
     "Search for flights from MIA to SEA on 2026-10-01.",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),
    ("flight-search-008", "flight_search", "flight-search", "tool_call_check", 2.0,
     "Find round-trip flights from BOS to LAX departing 2026-08-20 returning 2026-08-27.",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),
    ("flight-search-009", "flight_search", "flight-search", "tool_call_check", 2.0,
     "Are there any flights from PHX to DFW on 2026-11-15?",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),
    ("flight-search-010", "flight_search", "flight-search", "tool_call_check", 2.0,
     "Find the cheapest flights from JFK to ORD on 2026-07-10.",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),

    # Hotel search — 6 more
    ("hotel-search-005", "hotel_search", "hotel-search", "tool_call_check", 2.0,
     "Find hotels in Austin Texas from 2026-09-01 to 2026-09-04 for 2 guests.",
     ["search_hotels"], {"search_hotels": ["location", "check_in", "check_out"]}),
    ("hotel-search-006", "hotel_search", "hotel-search", "tool_call_check", 2.0,
     "Search for hotels near Times Square New York from 2026-12-28 to 2026-12-31.",
     ["search_hotels"], {"search_hotels": ["location", "check_in", "check_out"]}),
    ("hotel-search-007", "hotel_search", "hotel-search", "tool_call_check", 2.0,
     "What hotels are available in San Francisco from 2026-08-15 to 2026-08-18?",
     ["search_hotels"], {"search_hotels": ["location", "check_in", "check_out"]}),
    ("hotel-search-008", "hotel_search", "hotel-search", "tool_call_check", 2.0,
     "Find hotels in Boston for one night on 2026-10-10.",
     ["search_hotels"], {"search_hotels": ["location", "check_in", "check_out"]}),
    ("hotel-search-009", "hotel_search", "hotel-search", "tool_call_check", 2.0,
     "Search for hotels near JFK airport from 2026-07-01 to 2026-07-02.",
     ["search_hotels"], {"search_hotels": ["location", "check_in", "check_out"]}),
    ("hotel-search-010", "hotel_search", "hotel-search", "tool_call_check", 2.0,
     "Find luxury hotels in Las Vegas from 2026-09-20 to 2026-09-23.",
     ["search_hotels"], {"search_hotels": ["location", "check_in", "check_out"]}),

    # Booking flow — 4 more
    ("booking-flow-005", "booking_flow", "book-itinerary", "tool_call_check", 3.0,
     "Book flight FL456 for passenger James Miller (DOB 1975-08-12). Confirm the booking.",
     ["create_booking"], {"create_booking": ["flight_id", "passenger"]}),
    ("booking-flow-006", "booking_flow", "book-itinerary", "tool_call_check", 3.0,
     "Validate passenger Sarah Connor (DOB 1984-05-30) then book hotel HT789 for her.",
     ["validate_passenger", "create_booking"],
     {"validate_passenger": ["name", "dob"], "create_booking": ["hotel_id", "passenger"]}),
    ("booking-flow-007", "booking_flow", "book-itinerary", "tool_call_check", 3.0,
     "Check availability for flight FL999 on 2026-09-01 then book it for passenger Tom Hardy (DOB 1979-09-15).",
     ["check_availability", "create_booking"],
     {"check_availability": ["resource_id", "date"], "create_booking": ["flight_id", "passenger"]}),
    ("booking-flow-008", "booking_flow", "book-itinerary", "tool_call_check", 3.0,
     "Book hotel HT321 for passenger Diana Prince (DOB 1991-03-22) checking in 2026-11-10.",
     ["create_booking"], {"create_booking": ["hotel_id", "passenger"]}),

    # Fare rules — 3 more
    ("fare-rules-004", "fare_rules", "fare-rules", "llm_judge", 1.0,
     "What is the change fee for flight FL777? Can I change the date?",
     ["get_fare_rules"], {"get_fare_rules": ["flight_id"]}),
    ("fare-rules-005", "fare_rules", "fare-rules", "llm_judge", 1.0,
     "Does flight FL444 include a free checked bag?",
     ["get_fare_rules"], {"get_fare_rules": ["flight_id"]}),
    ("fare-rules-006", "fare_rules", "fare-rules", "llm_judge", 1.0,
     "What are the refund conditions for flight FL666?",
     ["get_fare_rules"], {"get_fare_rules": ["flight_id"]}),

    # Itinerary — 3 more
    ("itinerary-004", "itinerary_build", "book-itinerary", "llm_judge", 1.5,
     "Plan a 4-day business trip to Seattle from San Francisco: flights and hotel near downtown.",
     ["search_flights", "search_hotels"],
     {"search_flights": ["origin", "destination", "date"], "search_hotels": ["location", "check_in", "check_out"]}),
    ("itinerary-005", "itinerary_build", "book-itinerary", "llm_judge", 1.5,
     "Get the itinerary for booking BK99887766.",
     ["get_itinerary"], {"get_itinerary": ["booking_id"]}),
    ("itinerary-006", "itinerary_build", "book-itinerary", "llm_judge", 1.5,
     "Plan a weekend getaway from NYC to Miami: search for flights on 2026-08-07 and hotels for 3 nights.",
     ["search_flights", "search_hotels"],
     {"search_flights": ["origin", "destination", "date"], "search_hotels": ["location", "check_in", "check_out"]}),

    # Edge cases — 7 more
    ("edge-cancel-002", "edge_cases", "modify-booking", "tool_call_check", 0.5,
     "Cancel booking BK11223344 and tell me the refund amount.",
     ["cancel_booking"], {"cancel_booking": ["booking_id"]}),
    ("edge-cancel-003", "edge_cases", "modify-booking", "tool_call_check", 0.5,
     "I need to cancel my reservation BK55667788.",
     ["cancel_booking"], {"cancel_booking": ["booking_id"]}),
    ("edge-datechange-002", "edge_cases", "modify-booking", "tool_call_check", 0.5,
     "Change the travel date on booking BK44332211 to 2026-09-25.",
     ["modify_booking"], {"modify_booking": ["booking_id", "changes"]}),
    ("edge-datechange-003", "edge_cases", "modify-booking", "tool_call_check", 0.5,
     "Reschedule booking BK77665544 to 2026-10-15.",
     ["modify_booking"], {"modify_booking": ["booking_id", "changes"]}),
    ("edge-multileg-002", "edge_cases", "flight-search", "tool_call_check", 0.5,
     "Search for flights from BOS to DEN on 2026-07-15, then from DEN to LAX on 2026-07-19.",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),
    ("edge-multileg-003", "edge_cases", "flight-search", "tool_call_check", 0.5,
     "Find flights from JFK to ORD on 2026-08-01 and from ORD to SEA on 2026-08-05.",
     ["search_flights"], {"search_flights": ["origin", "destination", "date"]}),
    ("edge-availability-001", "edge_cases", "book-itinerary", "tool_call_check", 0.5,
     "Check if flight FL123 is available on 2026-07-15.",
     ["check_availability"], {"check_availability": ["resource_id", "date"]}),
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

for row in NEW_TASKS:
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

print(f"Created {len(NEW_TASKS)} new task directories in tasks/")
