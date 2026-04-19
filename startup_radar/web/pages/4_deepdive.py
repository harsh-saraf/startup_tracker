"""Company DeepDive — spawn the AI research-brief subprocess, surface past
reports, and show warm-intro candidates from LinkedIn connections.

Session-state reads/writes: ``DD_*`` constants in ``startup_radar.web.state``.
The subprocess handle (``DD_GEN_PROC``) is held across Streamlit reruns
until ``proc.poll()`` returns or the ``.docx`` appears on disk.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import database
from startup_radar.web import state
from startup_radar.web.cache import load_data
from startup_radar.web.lookup import lookup_company

TODAY = datetime.now().strftime("%Y-%m-%d")
# repo root: pages/4_deepdive.py -> pages -> web -> startup_radar -> repo
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
REPORTS_DIR = PROJECT_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def _report_path(company_name: str) -> Path:
    safe = company_name.strip().replace(" ", "")
    return REPORTS_DIR / f"{safe}_Research_Brief.docx"


def _investors_path(company_name: str) -> Path:
    safe = company_name.strip().replace(" ", "")
    return REPORTS_DIR / f"{safe}_investors.json"


df_startups, _ = load_data()

st.title("Company DeepDive")
st.caption("Generate a one-page research brief for any company")

if st.button("+ Add Company", key=state.DD_ADD_BTN):
    st.session_state[state.DD_SHOW_ADD] = not st.session_state.get(state.DD_SHOW_ADD, False)
    st.session_state.pop(state.DD_LOOKUP, None)
    st.session_state.pop(state.DD_LOOKUP_VERSION, None)

if st.session_state.get(state.DD_SHOW_ADD):
    dd_name = st.text_input("Company Name *", key=state.DD_NAME_INPUT)
    if st.button("Lookup", key=state.DD_LOOKUP_BTN):
        if dd_name.strip():
            with st.spinner(f"Looking up {dd_name.strip()}..."):
                info = lookup_company(dd_name.strip())
            if info:
                st.session_state[state.DD_LOOKUP] = info
                st.session_state[state.DD_LOOKUP_VERSION] = (
                    st.session_state.get(state.DD_LOOKUP_VERSION, 0) + 1
                )
                st.rerun()
            else:
                st.warning("No results found. Fill in details manually.")
        else:
            st.error("Enter a company name first.")

    lookup = st.session_state.get(state.DD_LOOKUP, {})
    ver = st.session_state.get(state.DD_LOOKUP_VERSION, 0)
    with st.form(f"add_company_dd_form_{ver}"):
        dd_desc = st.text_input("Description", value=lookup.get("description", ""))
        dd_stage = st.text_input("Funding Stage", value=lookup.get("funding_stage", ""))
        dd_amount = st.text_input("Amount Raised", value=lookup.get("amount_raised", ""))
        dd_loc = st.text_input("Location", value=lookup.get("location", ""))
        dd_submit = st.form_submit_button("Add Company")
    if dd_submit:
        if not dd_name.strip():
            st.error("Company Name is required.")
        else:
            inserted = database.insert_startups(
                [
                    {
                        "company_name": dd_name.strip(),
                        "description": dd_desc.strip(),
                        "funding_stage": dd_stage.strip(),
                        "amount_raised": dd_amount.strip(),
                        "location": dd_loc.strip(),
                        "source": "Manual",
                        "date_found": TODAY,
                        "status": "",
                    }
                ]
            )
            if inserted:
                st.session_state[state.DD_SHOW_ADD] = False
                st.session_state.pop(state.DD_LOOKUP, None)
                st.session_state.pop(state.DD_LOOKUP_VERSION, None)
                load_data.clear()
                st.rerun()
            else:
                st.warning(f"'{dd_name.strip()}' already exists.")

company_names = df_startups["Company Name"].tolist()
selected = st.selectbox("Select a company", [""] + company_names, key=state.DD_SELECT)

if selected:
    report = _report_path(selected)
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if report.exists():
            col_a, col_b = st.columns([1, 2])
            col_a.success("Report ready")
            with open(report, "rb") as f:
                col_b.download_button(
                    label="Download Research Brief",
                    data=f,
                    file_name=report.name,
                    mime=(
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    ),
                )
        elif st.session_state.get(state.DD_GENERATING) == selected:
            proc = st.session_state.get(state.DD_GEN_PROC)
            start = st.session_state.get(state.DD_GEN_START, time.time())
            if report.exists():
                st.session_state.pop(state.DD_GENERATING, None)
                st.session_state.pop(state.DD_GEN_PROC, None)
                st.session_state.pop(state.DD_GEN_START, None)
                st.success(f"Report for {selected} is ready.")
                st.rerun()
            elif proc is not None and proc.poll() is not None:
                st.session_state.pop(state.DD_GENERATING, None)
                st.session_state.pop(state.DD_GEN_PROC, None)
                st.session_state.pop(state.DD_GEN_START, None)
                if report.exists():
                    st.success("Report ready!")
                    st.rerun()
                else:
                    st.error("Report generation failed. Check logs.")
            else:
                elapsed = int(time.time() - start)
                pct = min(elapsed / 60.0, 0.95)
                stages = [
                    (0.0, "Starting research..."),
                    (0.1, "Searching for company info..."),
                    (0.25, "Gathering funding data..."),
                    (0.45, "Analyzing competitors..."),
                    (0.65, "Scoring company fit..."),
                    (0.8, "Generating report..."),
                ]
                label = stages[0][1]
                for threshold, stage_label in stages:
                    if pct >= threshold:
                        label = stage_label
                st.progress(pct, text=label)
                st.caption(f"Elapsed: {elapsed // 60}m {elapsed % 60}s")
                time.sleep(3)
                st.rerun()
        else:
            if st.button("Generate DeepDive Report", key=state.DD_GEN_BTN):
                proc = subprocess.Popen(
                    [
                        sys.executable or "python",
                        "-m",
                        "startup_radar.cli",
                        "deepdive",
                        selected,
                    ],
                    cwd=str(PROJECT_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                st.session_state[state.DD_GENERATING] = selected
                st.session_state[state.DD_GEN_PROC] = proc
                st.session_state[state.DD_GEN_START] = time.time()
                st.rerun()

    with btn_col2:
        if st.button("Find Warm Intros", key=state.DD_WARM_BTN):
            st.session_state[state.DD_SHOW_WARM] = selected
        elif st.session_state.get(state.DD_SHOW_WARM) != selected:
            st.session_state.pop(state.DD_SHOW_WARM, None)

    if st.session_state.get(state.DD_SHOW_WARM) == selected:
        if database.get_connections_count() == 0:
            st.warning(
                "No LinkedIn connections uploaded. Use the sidebar to upload your connections CSV."
            )
        else:
            with st.spinner(f"Searching connections for intros to {selected}..."):
                tier1 = database.search_connections_by_company(selected)

                investor_names: list[str] = []
                inv_path = _investors_path(selected)
                if inv_path.exists():
                    try:
                        investor_names = json.loads(inv_path.read_text())
                    except Exception:
                        pass
                elif report.exists():
                    try:
                        from docx import Document as DocxDocument

                        doc = DocxDocument(str(report))
                        full_text = "\n".join(p.text for p in doc.paragraphs)
                        for m in re.finditer(
                            r"(?:led by|investors?\s+include|backed by)\s+([^.]+)",
                            full_text,
                            re.IGNORECASE,
                        ):
                            for inv in re.split(r",\s*|\s+and\s+", m.group(1)):
                                inv = inv.strip().rstrip(".")
                                if inv and 2 < len(inv) < 50 and inv not in investor_names:
                                    investor_names.append(inv)
                    except Exception:
                        pass

                tier2 = (
                    database.search_connections_by_companies(investor_names)
                    if investor_names
                    else pd.DataFrame()
                )
                if not tier2.empty and not tier1.empty:
                    tier2 = tier2[~tier2["url"].isin(tier1["url"])]

                hidden = database.get_hidden_intros(selected)
                intro_rows = []
                for df_tier, tier_label in [(tier1, "Direct"), (tier2, "Investor")]:
                    if df_tier.empty:
                        continue
                    for _, c in df_tier.iterrows():
                        url = c.get("url", "") or ""
                        if url in hidden:
                            continue
                        name = f"{c['first_name']} {c['last_name']}".strip()
                        intro_rows.append(
                            {
                                "Tier": tier_label,
                                "Name": name,
                                "Position": c.get("position", ""),
                                "Company": c.get("company", ""),
                                "LinkedIn": url,
                                "Action": "",
                            }
                        )

            st.divider()
            if not intro_rows:
                if not investor_names:
                    st.info(
                        f"No direct connections at {selected}. Generate a DeepDive "
                        "report to unlock investor-based intros."
                    )
                else:
                    st.info(f"No connections found related to {selected}.")
            else:
                st.markdown(f"**{len(intro_rows)} connection(s) found**")
                _intro_df = pd.DataFrame(intro_rows)
                edited_intros = st.data_editor(
                    _intro_df,
                    column_config={
                        "LinkedIn": st.column_config.LinkColumn(
                            "LinkedIn", display_text="Profile", width="small"
                        ),
                        "Action": st.column_config.SelectboxColumn(
                            "Action",
                            options=["", "Save to Tracker", "Hide"],
                            width="small",
                        ),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key=state.DD_WARM_EDITOR,
                )
                _intros_changed = False
                for idx in edited_intros.index:
                    action = edited_intros.loc[idx, "Action"]
                    if not action:
                        continue
                    row = _intro_df.loc[idx]
                    if action == "Hide":
                        database.hide_intro(row["LinkedIn"], selected)
                        _intros_changed = True
                    elif action == "Save to Tracker":
                        database.insert_activity(
                            {
                                "company_name": selected,
                                "role_title": "",
                                "activity_type": "Note",
                                "contact_name": row["Name"],
                                "contact_title": f"{row['Position']} at {row['Company']}",
                                "contact_email": "",
                                "date": TODAY,
                                "follow_up_date": "",
                                "notes": f"Warm intro lead ({row['Tier']})",
                            }
                        )
                        _intros_changed = True
                if _intros_changed:
                    st.rerun()

st.divider()
st.subheader("Past Reports")
existing_reports = sorted(
    REPORTS_DIR.glob("*_Research_Brief.docx"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not existing_reports:
    st.caption("No reports generated yet. Select a company above to create one.")
else:
    for rpt in existing_reports:
        display_name = rpt.stem.replace("_Research_Brief", "")
        generated = datetime.fromtimestamp(rpt.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        col1, col2, col3 = st.columns([3, 2, 1])
        col1.markdown(f"**{display_name}**")
        col2.caption(f"Generated: {generated}")
        with open(rpt, "rb") as f:
            col3.download_button(
                label="Download",
                data=f,
                file_name=rpt.name,
                mime=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                key=f"dl_{rpt.stem}",
            )
