# eval/trigger_eval.py
"""Evaluate trigger routing accuracy per skill on labeled_requests.json."""
from __future__ import annotations
import argparse
import json
import os
import pathlib

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
{"skill": "<skill-name-or-null>", "confidence": <0.0-1.0>}

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


def compute_pr(labeled, predictions, skill: str) -> dict:
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
    print("-" * 60)
    print(f"{'Skill':<20} {'Precision':>9}  {'Recall':>6}  {'No-trig P':>9}")

    all_metrics = {}
    for skill in SKILLS:
        m = compute_pr(labeled, predictions, skill)
        all_metrics[skill] = m
        p_flag = "OK" if m["precision"] >= 0.85 else "<- below"
        r_flag = "OK" if m["recall"] >= 0.80 else "<- below"
        print(f"{skill:<20} {m['precision']:>9.2f} {p_flag:<10} {m['recall']:>6.2f} {r_flag}")

    pathlib.Path(args.output).write_text(json.dumps(all_metrics, indent=2))
    print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
