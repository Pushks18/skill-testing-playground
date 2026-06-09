# ui/app.py
"""Streamlit leaderboard for skill-testing-playground."""
import json
import pathlib
from collections import defaultdict
from datetime import datetime

import streamlit as st

st.set_page_config(page_title="Skill Leaderboard", layout="wide")

RESULTS_DIR = pathlib.Path("results")

def load_results():
    by_skill = defaultdict(list)
    for path in sorted(RESULTS_DIR.rglob("*_ab_results.json")):
        try:
            data = json.loads(path.read_text())
            for r in data:
                by_skill[r["skill_name"]].append(r)
        except Exception:
            continue
    return dict(by_skill)

def summarize(skill_name, results):
    total_w = sum(r.get("task_weight", 1.0) for r in results)
    weighted_delta = sum(r["delta"] * r.get("task_weight", 1.0) for r in results) / total_w if total_w else 0
    regression_rate = sum(1 for r in results if r["delta"] < 0) / len(results)
    regressions = [r for r in results if r["delta"] < 0]
    improvements = [r for r in results if r["delta"] > 0.05]
    return {
        "Skill": skill_name,
        "Weighted Δ": round(weighted_delta, 3),
        "Regression Rate": f"{regression_rate:.0%}",
        "Tasks": len(results),
        "Improvements": len(improvements),
        "Regressions": len(regressions),
        "Verdict": "✅ PASS" if regression_rate < 0.2 and weighted_delta >= 0 else "⚠️ WARN" if weighted_delta >= 0 else "❌ BLOCK",
    }

# --- Header ---
st.title("🧳 Skill Leaderboard")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

by_skill = load_results()

if not by_skill:
    st.warning("No results found. Run `python -m eval.ab_compare --skill <skill>` first.")
    st.stop()

# --- Summary table ---
summaries = [summarize(k, v) for k, v in by_skill.items()]
summaries.sort(key=lambda x: x["Weighted Δ"], reverse=True)

st.subheader("Summary")
import pandas as pd
df = pd.DataFrame(summaries)

def color_delta(val):
    if val > 0.1:
        return "color: #22c55e; font-weight: bold"
    elif val > 0:
        return "color: #86efac"
    elif val < 0:
        return "color: #ef4444; font-weight: bold"
    return ""

st.dataframe(
    df.style.map(color_delta, subset=["Weighted Δ"]),
    use_container_width=True,
    hide_index=True,
)

# --- Per-skill drill-down ---
st.subheader("Task-level detail")
selected = st.selectbox("Select skill", list(by_skill.keys()))

if selected:
    tasks = by_skill[selected]
    task_rows = []
    for r in sorted(tasks, key=lambda x: x["task_id"]):
        delta = r["delta"]
        flag = "✅" if delta > 0.05 else ("❌ REGRESSION" if delta < 0 else "–")
        task_rows.append({
            "Task": r["task_id"],
            "Domain": r["domain"],
            "Weight": r["task_weight"],
            "No Skill": round(r["no_skill"]["score"], 2),
            "With Skill": round(r["with_skill"]["score"], 2),
            "Δ": round(delta, 3),
            "Flag": flag,
        })
    task_df = pd.DataFrame(task_rows)
    st.dataframe(
        task_df.style.map(color_delta, subset=["Δ"]),
        use_container_width=True,
        hide_index=True,
    )

    # Mini bar chart
    st.bar_chart(task_df.set_index("Task")["Δ"])
