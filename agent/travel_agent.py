# agent/travel_agent.py
"""LangGraph travel agent with optional skill injection via system prompt."""
from __future__ import annotations
import os
import operator
import pathlib
import time as _time
import warnings
import httpx
import yaml
from typing import TypedDict, Optional, Annotated
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

MOCK_MCP_URL = os.environ.get("MOCK_MCP_URL", "http://localhost:8000")

_CONFIG_PATH = pathlib.Path(__file__).parent / "harness_config.yaml"

# Source-of-truth defaults — used when harness_config.yaml is absent or partial.
# These are the original hardcoded strings; the YAML overrides them when present.
HARNESS_DEFAULTS = {
    "base_system_prompt": (
        "You are a helpful travel assistant. "
        "Use the available tools to help users with flight searches, hotel bookings, and travel planning."
    ),
    "tool_descriptions": {
        "search_flights": "Search for available flights between two cities.",
        "search_hotels": "Search for available hotels at a location.",
        "check_availability": "Check if a flight or hotel resource is available on a date.",
        "get_fare_rules": "Get cancellation, change, and baggage rules for a flight.",
        "validate_passenger": "Validate passenger information before booking.",
        "create_booking": "Create a flight or hotel booking for a passenger.",
        "modify_booking": "Modify an existing booking (date change, upgrade, etc).",
        "cancel_booking": "Cancel a booking and get refund information.",
        "get_itinerary": "Retrieve the full itinerary for a booking.",
        "add_ancillary": "Add an ancillary service to a booking. service_type: seat_selection, extra_baggage, travel_insurance, lounge_access, priority_boarding, car_rental, airport_transfer.",
    },
    "node_prompts": {},
}


def load_harness_config(config_path: pathlib.Path = _CONFIG_PATH) -> dict:
    """Load harness config from YAML, falling back to HARNESS_DEFAULTS per key."""
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in HARNESS_DEFAULTS.items()}
    if config_path.exists():
        try:
            loaded = yaml.safe_load(config_path.read_text()) or {}
        except yaml.YAMLError as e:
            warnings.warn(f"harness_config parse error, using defaults: {e}")
            loaded = {}
        for key in HARNESS_DEFAULTS:
            if key in loaded and loaded[key] is not None:
                cfg[key] = loaded[key]
    return cfg


class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    tools_called: list
    step_timings: list
    response: str
    steps: int
    tokens_used: int
    input_tokens: int
    output_tokens: int


def make_mcp_tools(base_url: str):
    @tool
    def search_flights(origin: str, destination: str, date: str, passengers: int = 1) -> dict:
        """Search for available flights between two cities."""
        r = httpx.post(f"{base_url}/search_flights",
                       json={"origin": origin, "destination": destination,
                             "date": date, "passengers": passengers}, timeout=10)
        return r.json()

    @tool
    def search_hotels(location: str, check_in: str, check_out: str, guests: int = 1) -> dict:
        """Search for available hotels at a location."""
        r = httpx.post(f"{base_url}/search_hotels",
                       json={"location": location, "check_in": check_in,
                             "check_out": check_out, "guests": guests}, timeout=10)
        return r.json()

    @tool
    def check_availability(resource_id: str, date: str) -> dict:
        """Check if a flight or hotel resource is available on a date."""
        r = httpx.post(f"{base_url}/check_availability",
                       json={"resource_id": resource_id, "date": date}, timeout=10)
        return r.json()

    @tool
    def get_fare_rules(flight_id: str) -> dict:
        """Get cancellation, change, and baggage rules for a flight."""
        r = httpx.post(f"{base_url}/get_fare_rules",
                       json={"flight_id": flight_id}, timeout=10)
        return r.json()

    @tool
    def validate_passenger(name: str, dob: str, passport: str = None) -> dict:
        """Validate passenger information before booking."""
        r = httpx.post(f"{base_url}/validate_passenger",
                       json={"name": name, "dob": dob, "passport": passport}, timeout=10)
        return r.json()

    @tool
    def create_booking(passenger: dict, flight_id: str = None, hotel_id: str = None) -> dict:
        """Create a flight or hotel booking for a passenger."""
        r = httpx.post(f"{base_url}/create_booking",
                       json={"flight_id": flight_id, "hotel_id": hotel_id,
                             "passenger": passenger}, timeout=10)
        return r.json()

    @tool
    def modify_booking(booking_id: str, changes: dict) -> dict:
        """Modify an existing booking (date change, upgrade, etc)."""
        r = httpx.post(f"{base_url}/modify_booking",
                       json={"booking_id": booking_id, "changes": changes}, timeout=10)
        return r.json()

    @tool
    def cancel_booking(booking_id: str) -> dict:
        """Cancel a booking and get refund information."""
        r = httpx.post(f"{base_url}/cancel_booking",
                       json={"booking_id": booking_id}, timeout=10)
        return r.json()

    @tool
    def get_itinerary(booking_id: str) -> dict:
        """Retrieve the full itinerary for a booking."""
        r = httpx.post(f"{base_url}/get_itinerary",
                       json={"booking_id": booking_id}, timeout=10)
        return r.json()

    @tool
    def add_ancillary(booking_id: str, service_type: str, details: dict = {}) -> dict:
        """Add an ancillary service to a booking. service_type: seat_selection, extra_baggage, travel_insurance, lounge_access, priority_boarding, car_rental, airport_transfer."""
        r = httpx.post(f"{base_url}/add_ancillary",
                       json={"booking_id": booking_id, "service_type": service_type, "details": details}, timeout=10)
        return r.json()

    tools = [search_flights, search_hotels, check_availability, get_fare_rules,
             validate_passenger, create_booking, modify_booking, cancel_booking,
             get_itinerary, add_ancillary]
    # Config-driven descriptions: YAML (when present) overrides the docstrings,
    # making tool descriptions an optimizable harness artifact.
    descriptions = load_harness_config(_CONFIG_PATH)["tool_descriptions"]
    for t in tools:
        if t.name in descriptions:
            t.description = descriptions[t.name]
    return tools


def build_travel_agent(skill_content: Optional[str] = None, mock_mcp_url: str = MOCK_MCP_URL,
                       model: Optional[str] = None):
    tools = make_mcp_tools(mock_mcp_url)
    tool_map = {t.name: t for t in tools}

    config = load_harness_config(_CONFIG_PATH)
    system_prompt = config["base_system_prompt"]
    node_prompts = config.get("node_prompts") or {}
    if node_prompts.get("agent_node"):
        system_prompt += f"\n\n{node_prompts['agent_node']}"
    if skill_content:
        system_prompt += f"\n\n## Skill Instructions\n{skill_content}"

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=os.environ["OPENAI_API_KEY"],
    ).bind_tools(tools)

    def agent_node(state: AgentState) -> dict:
        msgs = [SystemMessage(content=system_prompt)] + state["messages"]
        response = llm.invoke(msgs)
        steps = state.get("steps", 0) + 1
        usage = getattr(response, "usage_metadata", None) or {}
        in_tok  = usage.get("input_tokens",  0)
        out_tok = usage.get("output_tokens", 0)
        return {
            "messages": [response],
            "tools_called": state.get("tools_called", []),
            "step_timings": state.get("step_timings", []),
            "steps": steps,
            "tokens_used":  state.get("tokens_used",  0) + in_tok + out_tok,
            "input_tokens": state.get("input_tokens",  0) + in_tok,
            "output_tokens": state.get("output_tokens", 0) + out_tok,
        }

    def tool_node(state: AgentState) -> dict:
        last = state["messages"][-1]
        tool_results = []
        tools_called = list(state.get("tools_called", []))
        step_timings = list(state.get("step_timings", []))
        for tc in getattr(last, "tool_calls", []):
            fn = tool_map.get(tc["name"])
            if fn:
                t0 = _time.time()
                result = fn.invoke(tc["args"])
                latency = int((_time.time() - t0) * 1000)
                tools_called.append({"name": tc["name"], "params": tc["args"]})
                step_timings.append({"tool": tc["name"], "latency_ms": latency, "tokens": 0})
                tool_results.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        return {"messages": tool_results, "tools_called": tools_called, "step_timings": step_timings}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    def format_response(state: AgentState) -> dict:
        last = state["messages"][-1]
        content = getattr(last, "content", str(last))
        return {"response": content}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("format", format_response)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: "format"})
    graph.add_edge("tools", "agent")
    graph.add_edge("format", END)

    return graph.compile()
