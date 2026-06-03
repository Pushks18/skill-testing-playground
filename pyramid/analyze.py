# pyramid/analyze.py
"""Analyze skill library and suggest atomic extractions + abstract inductions."""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import re

import openai

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


def load_all_skills(skills_dir):
    skills = {}
    for layer in ["atomic", "concrete", "abstract"]:
        layer_dir = pathlib.Path(skills_dir) / layer
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

    skills = load_all_skills(args.skills_dir)
    if not skills:
        print("No skills found.")
        return

    skills_block = "\n\n".join(f"### {name}\n{content}" for name, content in skills.items())
    prompt = ANALYZE_PROMPT.format(skills_block=skills_block)

    client = openai.OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )
    msg = client.chat.completions.create(
        model="google/gemini-2.5-flash",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.choices[0].message.content
    try:
        suggestions = json.loads(raw)
    except json.JSONDecodeError:
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
