# ui/pages/4_Task_Bank.py
"""Task Bank: browse coverage, add new tasks through the real QC gates, promote.

A human adds a task for a (possibly new) skill here. The form writes a draft
and runs the SAME gates the batch pipeline uses — structural validation,
embedding dedupe against the whole bank, and an optional live calibration
trial — and only a draft that passed validation + dedupe can be promoted.
No gate bypasses: this page calls eval/taskgen.py functions directly.
"""
from __future__ import annotations
import json
import pathlib
import shutil
import sys

import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

from eval.taskgen import (
    DOMAIN_TARGETS, DOMAIN_SKILL, DRAFTS_DIR, TASKS_DIR,
    parse_generated_tasks, validate_draft, find_near_duplicates,
    _existing_instructions, _next_suffix, calibrate_drafts,
)

st.set_page_config(page_title="Task Bank", layout="wide")
st.title("Task Bank")

APPROVED_TOOLS = json.loads(
    pathlib.Path("eval/security/approved_tools.json").read_text()
)["approved_mcp_tools"]

tab_overview, tab_add, tab_proposals = st.tabs(
    ["Bank Overview", "Add a Task", "Improvement Proposals"]
)

# ── Tab 1: Bank Overview ─────────────────────────────────────────────────────
with tab_overview:
    st.subheader("Coverage by skill")
    counts: dict[str, int] = {}
    for toml in TASKS_DIR.glob("*/task.toml"):
        for line in toml.read_text().splitlines():
            if line.startswith("skill"):
                counts[line.split('"')[1]] = counts.get(line.split('"')[1], 0) + 1
                break
    total = sum(counts.values())
    st.metric("Total tasks", total)
    cols = st.columns(4)
    for i, (skill, n) in enumerate(sorted(counts.items(), key=lambda x: -x[1])):
        cols[i % 4].metric(skill, n)
    st.caption(
        "Coverage is CI-enforced: tests/test_skill_task_coverage.py fails the "
        "build if an evaluable skill drops below 10 tasks or a task points at "
        "a skill that doesn't exist."
    )

    st.subheader("Browse tasks")
    domain_filter = st.selectbox("Domain", ["all"] + sorted(DOMAIN_TARGETS))
    query = st.text_input("Search instruction text")
    shown = 0
    for td in sorted(TASKS_DIR.iterdir()):
        if shown >= 50:
            st.caption("…showing first 50 matches")
            break
        toml_p, instr_p = td / "task.toml", td / "instruction.md"
        if not (toml_p.exists() and instr_p.exists()):
            continue
        toml_text, instr = toml_p.read_text(), instr_p.read_text().strip()
        if domain_filter != "all" and f'domain = "{domain_filter}"' not in toml_text:
            continue
        if query and query.lower() not in instr.lower():
            continue
        with st.expander(f"{td.name} — {instr[:90]}"):
            st.code(toml_text, language="toml")
            st.markdown(f"> {instr}")
        shown += 1

# ── Tab 2: Add a Task ────────────────────────────────────────────────────────
with tab_add:
    st.subheader("Add a task — passes the same gates as the batch pipeline")

    domain = st.selectbox("Domain (maps to the skill that owns it)", sorted(DOMAIN_TARGETS))
    _, default_weight, prefix = DOMAIN_TARGETS[domain]
    st.caption(f"Owning skill: **{DOMAIN_SKILL[domain]}** · task id prefix: `{prefix}-` · default weight: {default_weight}")

    instruction = st.text_area(
        "Instruction (the user message the agent will receive)",
        placeholder="e.g. Check availability for flight FL123 on 2026-09-10 and book it for Jane Doe (DOB 1990-01-01).",
        height=90,
    )
    verifier = st.radio("Verifier", ["tool_call_check", "llm_judge"], horizontal=True,
                        help="tool_call_check: mechanical — required tools + params present. "
                             "llm_judge: 3-vote LLM scoring against pass criteria.")
    weight = st.number_input("Weight (3.0 = business-critical; trips tier-1 gate alone)",
                             value=float(default_weight), min_value=0.5, max_value=5.0, step=0.5)

    tools, required_params, criteria = [], {}, ""
    if verifier == "tool_call_check":
        tools = st.multiselect("Required tools (must all be called)", APPROVED_TOOLS)
        for t in tools:
            p = st.text_input(f"Required params for {t} (comma-separated, blank = none)", key=f"p_{t}")
            if p.strip():
                required_params[t] = [x.strip() for x in p.split(",") if x.strip()]
    else:
        criteria = st.text_area("Pass criteria (what the judge must see in the answer)", height=70)

    if st.button("Run gates", type="primary", disabled=not instruction.strip()):
        item = {
            "id_suffix": f"{_next_suffix(domain):03d}",
            "instruction": instruction.strip(),
            "verifier": verifier,
            "tools": tools,
            "required_params": required_params,
            "criteria": criteria,
        }
        out_dir = DRAFTS_DIR / domain
        draft = parse_generated_tasks(json.dumps([item]), domain, out_dir)[0]
        # weight override (parse_generated_tasks uses the domain default)
        toml_p = draft / "task.toml"
        toml_p.write_text(toml_p.read_text().replace(
            f"weight = {default_weight}", f"weight = {weight}", 1))
        st.session_state["draft_path"] = str(draft)

        errors = validate_draft(draft)
        dups = find_near_duplicates(
            {draft.name: instruction.strip()}, _existing_instructions(domain), threshold=0.90)
        st.session_state["gates_ok"] = not errors and not dups

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Gate 1 — structural validation**")
            st.error("\n".join(errors)) if errors else st.success("valid")
        with c2:
            st.markdown("**Gate 2 — dedupe vs entire bank (cosine ≥ 0.90)**")
            if dups:
                st.error("\n".join(f"near-duplicate of {b} (cos {s:.2f})" for _, b, s in dups))
            else:
                st.success("novel")

    if st.session_state.get("draft_path"):
        draft = pathlib.Path(st.session_state["draft_path"])
        if draft.exists():
            st.code((draft / "task.toml").read_text(), language="toml")

            col_cal, col_promote, col_discard = st.columns(3)
            with col_cal:
                if st.button("Gate 3 — calibrate (1 live no-skill trial)"):
                    with st.spinner("Running the agent once against the mock server…"):
                        report = calibrate_drafts([draft], "http://localhost:8000")
                    r = report.get(draft.name, {})
                    st.info(f"**{r.get('class', '?')}** — {r.get('detail', '')}")
                    if r.get("class") == "broken":
                        st.session_state["gates_ok"] = False
            with col_promote:
                if st.button("Promote to bank", type="primary",
                             disabled=not st.session_state.get("gates_ok")):
                    dst = TASKS_DIR / draft.name
                    if dst.exists():
                        st.error(f"{draft.name} already exists in the bank")
                    elif validate_draft(draft):
                        st.error("draft no longer validates — re-run gates")
                    else:
                        shutil.copytree(draft, dst)
                        st.success(f"Promoted → tasks/{draft.name}. "
                                   "Commit it so CI and future evals pick it up.")
                        st.session_state.pop("draft_path", None)
            with col_discard:
                if st.button("Discard draft"):
                    shutil.rmtree(draft, ignore_errors=True)
                    st.session_state.pop("draft_path", None)
                    st.rerun()

    st.caption(
        "New skill with no domain yet? Add one line to DOMAIN_TARGETS/DOMAIN_SKILL in "
        "eval/taskgen.py first — the coverage test will hold CI red until the new "
        "skill has at least 10 promoted tasks."
    )

# ── Tab 3: Improvement Proposals ─────────────────────────────────────────────
with tab_proposals:
    st.subheader("Which skills need a skill update vs a harness update")
    proposals_dir = pathlib.Path("proposals")
    if not proposals_dir.exists():
        st.warning("proposals/ folder not found")
    else:
        index = proposals_dir / "README.md"
        if index.exists():
            st.markdown(index.read_text())
        for f in sorted(proposals_dir.glob("*.md")):
            if f.name == "README.md":
                continue
            with st.expander(f.stem.replace("-", " ")):
                st.markdown(f.read_text())
