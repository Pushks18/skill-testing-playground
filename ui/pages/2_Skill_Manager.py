# ui/pages/2_Skill_Manager.py
"""Skill management UI: browse, edit, create, and run evals."""
from __future__ import annotations
import pathlib
import sys

import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

from eval.skill_manager import (
    list_skills, read_skill, write_skill, commit_skill,
    get_skill_history, run_eval, load_last_eval_results,
    validate_skill, LAYERS,
)

st.set_page_config(page_title="Skill Manager", layout="wide")
st.title("Skill Manager")

tab1, tab2, tab3 = st.tabs(["Browse", "Edit / Create", "Run Eval"])

# ── Tab 1: Browse ─────────────────────────────────────────────────────────────
with tab1:
    st.subheader("Skill Library")
    skills = list_skills()
    if not skills:
        st.warning("No skills found in skills/ directory.")
    else:
        for layer in LAYERS:
            layer_skills = [s for s in skills if s.layer == layer]
            if not layer_skills:
                continue
            st.markdown(f"### {layer.capitalize()} ({len(layer_skills)})")
            for skill in layer_skills:
                eval_data = load_last_eval_results(skill.name)
                delta_str = f"Δ {eval_data['weighted_delta']:+.3f}" if eval_data else "not evaluated"
                regr_str = f" | regr {eval_data['regression_rate']:.0%}" if eval_data else ""
                with st.expander(f"**{skill.name}** — {delta_str}{regr_str} — last commit: {skill.last_commit} ({skill.last_modified})"):
                    st.code(skill.content, language="markdown")
                    history = get_skill_history(skill.layer, skill.name)
                    if history:
                        st.markdown("**Recent commits:**")
                        for h in history:
                            st.markdown(f"- `{h['hash']}` {h['message']}")

# ── Tab 2: Edit / Create ──────────────────────────────────────────────────────
with tab2:
    st.subheader("Edit or Create a Skill")
    col1, col2 = st.columns([1, 3])
    with col1:
        mode = st.radio("Mode", ["Edit existing", "Create new"])
        selected_layer = st.selectbox("Layer", LAYERS)

    if mode == "Edit existing":
        layer_skills = [s for s in list_skills() if s.layer == selected_layer]
        if not layer_skills:
            st.info(f"No {selected_layer} skills yet.")
        else:
            skill_names = [s.name for s in layer_skills]
            with col1:
                selected_name = st.selectbox("Skill", skill_names)
            initial_content = read_skill(selected_layer, selected_name)
            with col2:
                edited_content = st.text_area("SKILL.md content", value=initial_content, height=450,
                                               key=f"editor_{selected_layer}_{selected_name}")
                errors = validate_skill(edited_content)
                if errors:
                    for e in errors:
                        st.error(f"Validation: {e}")
                else:
                    st.success("Format valid")
                commit_msg = st.text_input("Commit message", value=f"feat: update skill {selected_name}")
                if st.button("Save & Commit", disabled=bool(errors)):
                    try:
                        write_skill(selected_layer, selected_name, edited_content)
                        result = commit_skill(selected_layer, selected_name, commit_msg)
                        st.success(f"Saved and committed: {result}")
                    except Exception as exc:
                        st.error(str(exc))
    else:
        with col1:
            selected_name = st.text_input("New skill name (e.g. car-rental)")
        initial_content = f"# {selected_name or 'new-skill'}\n\n## When to Use\n\n## Workflow\n1. \n\n## When NOT to Use\n- \n"
        with col2:
            edited_content = st.text_area("SKILL.md content", value=initial_content, height=450,
                                           key=f"create_{selected_layer}_{selected_name}")
            errors = validate_skill(edited_content)
            if errors:
                for e in errors:
                    st.error(f"Validation: {e}")
            else:
                st.success("Format valid")
            commit_msg = st.text_input("Commit message", value=f"feat: add skill {selected_name or 'new'}")
            if st.button("Save & Commit", disabled=bool(errors) or not selected_name):
                try:
                    write_skill(selected_layer, selected_name, edited_content)
                    result = commit_skill(selected_layer, selected_name, commit_msg)
                    st.success(f"Created and committed: {result}")
                except Exception as exc:
                    st.error(str(exc))

# ── Tab 3: Run Eval ───────────────────────────────────────────────────────────
with tab3:
    st.subheader("Run A/B Eval")
    skills = list_skills()
    if not skills:
        st.info("No skills found.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            eval_layer = st.selectbox("Layer ", LAYERS, key="eval_layer")
        with col2:
            layer_skills = [s.name for s in skills if s.layer == eval_layer]
            eval_skill = st.selectbox("Skill ", layer_skills, key="eval_skill") if layer_skills else None
        with col3:
            trials = st.selectbox("Trials", [2, 3, 5, 10], index=1)

        if eval_skill and st.button(f"Run eval: {eval_layer}/{eval_skill} (N={trials})"):
            with st.spinner(f"Running A/B eval for {eval_skill}..."):
                output = run_eval(eval_layer, eval_skill, trials)
            st.code(output, language="text")
            eval_data = load_last_eval_results(eval_skill)
            if eval_data:
                c1, c2 = st.columns(2)
                c1.metric("Weighted Δ", f"{eval_data['weighted_delta']:+.3f}")
                c2.metric("Regression Rate", f"{eval_data['regression_rate']:.0%}")
