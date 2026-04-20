"""Job Matches — wishlist / interested / not-interested / uncategorized
tables with inline editor + "Add Role" form.

Session-state reads/writes: ``JOB_*`` constants in ``startup_radar.web.state``.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from startup_radar.web import state
from startup_radar.web.cache import get_storage, load_data

storage = get_storage()

TODAY = datetime.now().strftime("%Y-%m-%d")
STATUS_OPTIONS = ["", "Interested", "Not Interested", "Applied", "Wishlist"]

df_startups, df_jobs = load_data()


def _get_connections_for_companies(company_names):
    result = {}
    for name in company_names:
        conns = storage.search_connections_by_company(name)
        if not conns.empty:
            parts = []
            for _, c in conns.iterrows():
                full_name = f"{c['first_name']} {c['last_name']}".strip()
                pos = c.get("position", "")
                parts.append(f"{full_name} ({pos})" if pos else full_name)
            result[name] = ", ".join(parts)
        else:
            result[name] = ""
    return result


def _add_job_connections_col(frame):
    frame = frame.copy()
    if storage.get_connections_count() == 0:
        frame["Connections"] = ""
        return frame
    conn_map = _get_connections_for_companies(frame["Company"].tolist())
    frame["Connections"] = frame["Company"].map(conn_map).fillna("")
    return frame


def _add_delete_col(frame):
    frame = frame.copy()
    frame["\U0001f5d1\ufe0f"] = False
    return frame


st.title("Job Matches")

if st.button("+ Add Role", key=state.JOB_ADD_BTN):
    st.session_state[state.JOB_SHOW_ADD] = not st.session_state.get(state.JOB_SHOW_ADD, False)

if st.session_state.get(state.JOB_SHOW_ADD):
    company_options = ["-- New company --"] + df_startups["Company Name"].tolist()
    with st.form("add_role_form"):
        ar_company = st.selectbox("Company", company_options)
        ar_new_company = st.text_input("New Company Name (if above is '-- New company --')")
        ar_role = st.text_input("Role Title *")
        ar_desc = st.text_input("Company Description")
        ar_loc = st.text_input("Location")
        ar_url = st.text_input("URL")
        ar_priority = st.selectbox("Priority", ["", "High", "Medium", "Low"])
        ar_submit = st.form_submit_button("Add Role")
    if ar_submit:
        company_name = ar_new_company.strip() if ar_company == "-- New company --" else ar_company
        if not company_name:
            st.error("Company is required.")
        elif not ar_role.strip():
            st.error("Role Title is required.")
        else:
            inserted = storage.insert_job_matches(
                [
                    {
                        "company_name": company_name,
                        "company_description": ar_desc.strip(),
                        "role_title": ar_role.strip(),
                        "location": ar_loc.strip(),
                        "url": ar_url.strip(),
                        "priority": ar_priority,
                        "status": "",
                        "date_found": TODAY,
                    }
                ]
            )
            if inserted:
                st.session_state[state.JOB_SHOW_ADD] = False
                load_data.clear()
                st.rerun()
            else:
                st.warning(f"Role '{ar_role.strip()}' at '{company_name}' already exists.")

job_search = st.text_input("Search", placeholder="Company name or role...", key=state.JOB_SEARCH)
filtered_jobs = df_jobs.copy()
if job_search:
    mask = filtered_jobs["Role"].str.contains(job_search, case=False, na=False) | filtered_jobs[
        "Company"
    ].str.contains(job_search, case=False, na=False)
    filtered_jobs = filtered_jobs[mask]

job_status_lower = filtered_jobs["Status"].str.strip().str.lower()
wishlist_jobs = filtered_jobs[job_status_lower == "wishlist"]
interested_jobs = filtered_jobs[job_status_lower == "interested"]
ni_jobs = filtered_jobs[job_status_lower == "not interested"]
uncategorized_jobs = filtered_jobs[
    ~job_status_lower.isin(["applied", "wishlist", "interested", "not interested"])
]

display_cols = [c for c in filtered_jobs.columns if c != "Priority"]

_job_col_config = {
    "Status": st.column_config.SelectboxColumn("Status", options=STATUS_OPTIONS, width="medium"),
    "Link": st.column_config.LinkColumn("Link", display_text="Apply"),
    "Connections": st.column_config.TextColumn("Connections", width="medium"),
    "\U0001f5d1\ufe0f": st.column_config.CheckboxColumn("\U0001f5d1\ufe0f", width="small"),
}


def _persist_job_changes(original_df, edited_df):
    changed = False
    for idx in edited_df.index:
        if idx not in original_df.index:
            continue
        if edited_df.loc[idx, "\U0001f5d1\ufe0f"]:
            storage.delete_job_match(original_df.loc[idx, "Company"], original_df.loc[idx, "Role"])
            changed = True
            continue
        old = original_df.loc[idx, "Status"]
        new = edited_df.loc[idx, "Status"]
        if old != new:
            company = original_df.loc[idx, "Company"]
            role = original_df.loc[idx, "Role"]
            storage.update_job_status(company, role, new)
            if new == "Applied":
                ts = storage.get_tracker_status(company)
                if not ts:
                    storage.upsert_tracker_status(company, "Applied", role, "")
                    storage.insert_activity(
                        {
                            "company_name": company,
                            "role_title": role,
                            "activity_type": "Applied",
                            "contact_name": "",
                            "contact_title": "",
                            "contact_email": "",
                            "date": TODAY,
                            "follow_up_date": "",
                            "notes": "",
                        }
                    )
            changed = True
    if changed:
        load_data.clear()
    return changed


_jobs_needs_rerun = False

st.subheader(f"Wishlist ({len(wishlist_jobs)})")
if wishlist_jobs.empty:
    st.caption("No wishlisted jobs yet.")
else:
    edited = st.data_editor(
        _add_delete_col(_add_job_connections_col(wishlist_jobs[display_cols])),
        column_config=_job_col_config,
        hide_index=True,
        use_container_width=True,
        disabled=[],
        key=state.JOB_WL_EDITOR,
    )
    if _persist_job_changes(wishlist_jobs, edited):
        _jobs_needs_rerun = True

st.divider()

st.subheader(f"Interested ({len(interested_jobs)})")
if interested_jobs.empty:
    st.caption("No jobs marked as interested yet.")
else:
    edited = st.data_editor(
        _add_delete_col(_add_job_connections_col(interested_jobs[display_cols])),
        column_config=_job_col_config,
        hide_index=True,
        use_container_width=True,
        disabled=[],
        key=state.JOB_INT_EDITOR,
    )
    if _persist_job_changes(interested_jobs, edited):
        _jobs_needs_rerun = True

st.divider()

with st.expander(f"Not Interested ({len(ni_jobs)})"):
    if ni_jobs.empty:
        st.caption("No jobs marked as not interested.")
    else:
        edited = st.data_editor(
            _add_delete_col(ni_jobs[display_cols]),
            column_config=_job_col_config,
            hide_index=True,
            use_container_width=True,
            disabled=[],
            key=state.JOB_NI_EDITOR,
        )
        if _persist_job_changes(ni_jobs, edited):
            _jobs_needs_rerun = True

st.divider()

st.subheader(f"Uncategorized ({len(uncategorized_jobs)})")
if uncategorized_jobs.empty:
    st.caption("All jobs have been categorized.")
else:
    edited = st.data_editor(
        _add_delete_col(_add_job_connections_col(uncategorized_jobs[display_cols])),
        column_config=_job_col_config,
        hide_index=True,
        use_container_width=True,
        disabled=[],
        key=state.JOB_UNC_EDITOR,
    )
    if _persist_job_changes(uncategorized_jobs, edited):
        _jobs_needs_rerun = True

if _jobs_needs_rerun:
    st.rerun()
