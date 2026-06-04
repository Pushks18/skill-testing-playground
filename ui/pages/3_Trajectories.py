# ui/pages/3_Trajectories.py
"""Trajectory viewer: failure breakdown + per-run step timeline."""
from __future__ import annotations
import pathlib
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

from eval.trajectory import get_runs, FAILURE_MODES, TrajectoryRun

st.set_page_config(page_title="Trajectories", layout="wide")
st.title("Agent Trajectory Viewer")

DB = pathlib.Path("trajectory.db")
if not DB.exists():
    st.warning("No trajectory data yet. Run `python -m eval.ab_compare` first.")
    st.stop()

# --- Sidebar filters ---
st.sidebar.header("Filters")
skill_filter = st.sidebar.text_input("Skill name (leave blank for all)", "")
task_filter = st.sidebar.text_input("Task ID (leave blank for all)", "")
failed_only = st.sidebar.checkbox("Failed runs only", value=False)

runs: list = get_runs(
    skill_name=skill_filter or None,
    task_id=task_filter or None,
    failed_only=failed_only,
    limit=500,
)

if not runs:
    st.info("No runs match the current filters.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Failure Breakdown", "Run Timeline", "No-Skill vs With-Skill"])

# ── Tab 1 ─────────────────────────────────────────────────────────────────────
with tab1:
    st.subheader(f"Failure breakdown ({len(runs)} runs)")
    failed_runs = [r for r in runs if not r.passed]
    passed_runs = [r for r in runs if r.passed]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total runs", len(runs))
    col2.metric("Passed", len(passed_runs))
    col3.metric("Failed", len(failed_runs))

    if failed_runs:
        from collections import Counter
        mode_counts = Counter(r.failure_mode or "UNKNOWN" for r in failed_runs)
        mode_df = pd.DataFrame([
            {"Failure Mode": k, "Count": v, "% of failures": f"{v/len(failed_runs):.0%}"}
            for k, v in sorted(mode_counts.items(), key=lambda x: -x[1])
        ])
        st.dataframe(mode_df, use_container_width=True, hide_index=True)
        st.bar_chart(mode_df.set_index("Failure Mode")["Count"])

        st.subheader("Failed run details")
        fail_rows = []
        for r in failed_runs:
            fail_rows.append({
                "Run ID": r.run_id[:8],
                "Task": r.task_id,
                "Skill": r.skill_name or "—",
                "Condition": r.condition,
                "Score": round(r.score, 2),
                "Failure Mode": r.failure_mode or "UNKNOWN",
                "Steps": len(r.steps),
            })
        st.dataframe(pd.DataFrame(fail_rows), use_container_width=True, hide_index=True)
    else:
        st.success("No failures in current filter set.")

# ── Tab 2 ─────────────────────────────────────────────────────────────────────
with tab2:
    st.subheader("Step-by-step timeline")
    run_ids = [f"{r.run_id[:8]} | {r.task_id} | {r.condition} | score={r.score:.2f}" for r in runs]
    selected_label = st.selectbox("Select run", run_ids)
    selected_idx = run_ids.index(selected_label)
    selected_run = runs[selected_idx]

    status = "✅ PASSED" if selected_run.passed else f"❌ FAILED — {selected_run.failure_mode or 'UNKNOWN'}"
    st.markdown(f"**Status:** {status}  |  **Score:** {selected_run.score:.2f}  |  **Total steps:** {len(selected_run.steps)}")

    if selected_run.steps:
        step_rows = []
        for s in selected_run.steps:
            step_rows.append({
                "Step": s.step_num,
                "Node": s.node,
                "Tool": s.tool_name or "—",
                "Params": str(s.tool_params) if s.tool_params else "—",
                "Latency (ms)": s.latency_ms,
                "Tokens": s.tokens,
            })
        st.dataframe(pd.DataFrame(step_rows), use_container_width=True, hide_index=True)
        if len(step_rows) > 1:
            st.bar_chart(pd.DataFrame(step_rows).set_index("Step")["Latency (ms)"])
    else:
        st.info("No tool steps recorded (agent responded without calling tools).")

# ── Tab 3 ─────────────────────────────────────────────────────────────────────
with tab3:
    st.subheader("No-skill vs with-skill comparison")
    task_ids = sorted(set(r.task_id for r in runs))
    selected_task = st.selectbox("Select task", task_ids)

    no_skill_runs = [r for r in runs if r.task_id == selected_task and r.condition == "no_skill"]
    with_skill_runs = [r for r in runs if r.task_id == selected_task and r.condition == "with_skill"]

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Without skill**")
        if no_skill_runs:
            r = no_skill_runs[0]
            st.metric("Score", round(r.score, 2))
            st.metric("Steps", len(r.steps))
            st.metric("Status", "PASS" if r.passed else f"FAIL: {r.failure_mode}")
            st.write("Tools called:", [s.tool_name for s in r.steps if s.tool_name] or ["none"])
        else:
            st.info("No no-skill runs for this task.")
    with col_b:
        st.markdown("**With skill**")
        if with_skill_runs:
            r = with_skill_runs[0]
            st.metric("Score", round(r.score, 2))
            st.metric("Steps", len(r.steps))
            st.metric("Status", "PASS" if r.passed else f"FAIL: {r.failure_mode}")
            st.write("Tools called:", [s.tool_name for s in r.steps if s.tool_name] or ["none"])
        else:
            st.info("No with-skill runs for this task.")
