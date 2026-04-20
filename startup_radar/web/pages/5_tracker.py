"""Application Tracker — reminders, applied pipeline, activity log,
rejected bucket. This is the longest page; state is entirely local.

Session-state reads/writes: ``AP_*`` and ``AL_*`` constants in
``startup_radar.web.state``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from startup_radar.web import state
from startup_radar.web.cache import get_storage, load_data

storage = get_storage()

TODAY = datetime.now().strftime("%Y-%m-%d")
ACTIVITY_TYPES = ["Emailed", "Applied", "Called", "Meeting", "Follow-up", "Interview", "Note"]
TRACKER_STATUS_OPTIONS = ["In Progress", "Applied", "Gone Cold"]
APPLIED_STATUS_OPTIONS = [
    "Applied",
    "Recruiter Screen",
    "Round 1 Interview",
    "Round 2 Interview",
    "Round 3 Interview",
    "Case Study",
    "Rejected",
]

df_startups, _ = load_data()

st.title("Application Tracker")

if st.button("+ Log Activity", key=state.AP_ADD_ACTIVITY_BTN):
    st.session_state[state.AP_SHOW_ADD_ACTIVITY] = not st.session_state.get(
        state.AP_SHOW_ADD_ACTIVITY, False
    )

if st.session_state.get(state.AP_SHOW_ADD_ACTIVITY):
    company_opts = [""] + df_startups["Company Name"].tolist()
    with st.form("add_activity_form"):
        act_company = st.selectbox("Company *", company_opts)
        act_role = st.text_input("Role Title (optional)")
        act_type = st.selectbox("Activity Type *", ACTIVITY_TYPES)
        act_contact = st.text_input("Contact Name")
        act_title = st.text_input("Contact Title")
        act_email = st.text_input("Contact Email")
        act_date = st.date_input("Date *", value=datetime.now())
        act_followup = st.date_input("Follow-up Date (optional)", value=None)
        act_notes = st.text_area("Notes")
        act_submit = st.form_submit_button("Log Activity")
    if act_submit:
        if not act_company:
            st.error("Company is required.")
        else:
            storage.insert_activity(
                {
                    "company_name": act_company,
                    "role_title": act_role.strip(),
                    "activity_type": act_type,
                    "contact_name": act_contact.strip(),
                    "contact_title": act_title.strip(),
                    "contact_email": act_email.strip(),
                    "date": act_date.strftime("%Y-%m-%d"),
                    "follow_up_date": act_followup.strftime("%Y-%m-%d") if act_followup else "",
                    "notes": act_notes.strip(),
                }
            )
            st.session_state[state.AP_SHOW_ADD_ACTIVITY] = False
            st.rerun()

# Reminders ----------------------------------------------------------------
_reminders = []
_overdue_tracker = storage.get_overdue_followups(TODAY)
for _, row in _overdue_tracker.iterrows():
    _is_overdue = row["follow_up_date"] < TODAY
    _contact = f" \u2014 {row['contact_name']}" if row.get("contact_name") else ""
    _role = f" \u00b7 {row['role_title']}" if row.get("role_title") else ""
    _reminders.append(
        {
            "icon": "\U0001f534" if _is_overdue else "\U0001f7e1",
            "text": f"**{row['company_name']}**{_role}{_contact}",
            "detail": (
                f"Scheduled follow-up due: {row['follow_up_date']} \u00b7 {row.get('notes', '')}"
            ),
        }
    )

_all_acts = storage.get_activities()
if not _all_acts.empty:
    _email_acts = _all_acts[_all_acts["activity_type"] == "Emailed"]
    if not _email_acts.empty:
        _today_dt = datetime.now()
        _seen_keys: set[str] = set()
        for _, act in _email_acts.iterrows():
            key = f"{act['company_name']}|{act['contact_name']}"
            if key in _seen_keys:
                continue
            _seen_keys.add(key)
            try:
                start = datetime.strptime(act["date"], "%Y-%m-%d")
            except Exception:
                continue
            bdays = 0
            current = start + timedelta(days=1)
            while current <= _today_dt:
                if current.weekday() < 5:
                    bdays += 1
                current += timedelta(days=1)
            if bdays >= 3:
                _contact = f" \u2014 {act['contact_name']}" if act.get("contact_name") else ""
                icon = "\U0001f534" if bdays >= 5 else "\U0001f7e1"
                urgency = f"{bdays} business days since last email"
                _has_scheduled = any(act["company_name"] in r.get("text", "") for r in _reminders)
                if not _has_scheduled:
                    _reminders.append(
                        {
                            "icon": icon,
                            "text": f"**{act['company_name']}**{_contact}",
                            "detail": f"Last emailed: {act['date']} \u2014 {urgency}",
                        }
                    )

if _reminders:
    st.subheader(f"Reminders ({len(_reminders)})")
    for r in _reminders:
        st.markdown(f"{r['icon']} {r['text']}  \n{r['detail']}")
    st.divider()

tracker_summary = storage.get_tracker_summary()
_activity_log_statuses = ["In Progress", "Gone Cold"]
_applied_tracker = (
    tracker_summary[~tracker_summary["Status"].isin(_activity_log_statuses + ["Rejected"])].copy()
    if not tracker_summary.empty
    else pd.DataFrame()
)
_active_tracker = (
    tracker_summary[tracker_summary["Status"].isin(_activity_log_statuses)].copy()
    if not tracker_summary.empty
    else pd.DataFrame()
)
_rejected_tracker = (
    tracker_summary[tracker_summary["Status"] == "Rejected"].copy()
    if not tracker_summary.empty
    else pd.DataFrame()
)

# Applied ------------------------------------------------------------------
st.divider()
st.subheader("Applied")

if st.button("+ Add Application", key=state.AP_ADD_APPLIED_BTN):
    st.session_state[state.AP_SHOW_ADD_APPLIED] = not st.session_state.get(
        state.AP_SHOW_ADD_APPLIED, False
    )

if st.session_state.get(state.AP_SHOW_ADD_APPLIED):
    with st.form("add_applied_form"):
        ap_company = st.selectbox(
            "Company *", [""] + df_startups["Company Name"].tolist(), key=state.AP_COMPANY
        )
        ap_new = st.text_input("Or enter new company name")
        ap_role = st.text_input("Role Title *", key=state.AP_ROLE)
        ap_status = st.selectbox("Status", APPLIED_STATUS_OPTIONS, key=state.AP_STATUS)
        ap_contact = st.text_input("Contact Name", key=state.AP_CONTACT)
        ap_contact_title = st.text_input("Contact Title", key=state.AP_CONTACT_TITLE)
        ap_date = st.date_input("Date Applied *", value=datetime.now(), key=state.AP_DATE)
        ap_notes = st.text_area("Notes", key=state.AP_NOTES)
        ap_submit = st.form_submit_button("Add Application")
    if ap_submit:
        company_name = ap_new.strip() if ap_new.strip() else ap_company
        if not company_name:
            st.error("Company is required.")
        elif not ap_role.strip():
            st.error("Role Title is required.")
        else:
            storage.insert_activity(
                {
                    "company_name": company_name,
                    "role_title": ap_role.strip(),
                    "activity_type": "Applied",
                    "contact_name": ap_contact.strip(),
                    "contact_title": ap_contact_title.strip(),
                    "contact_email": "",
                    "date": ap_date.strftime("%Y-%m-%d"),
                    "follow_up_date": "",
                    "notes": ap_notes.strip(),
                }
            )
            storage.upsert_tracker_status(
                company_name, ap_status, ap_role.strip(), ap_notes.strip()
            )
            existing_keys = storage.get_existing_job_keys()
            key = f"{company_name.lower().strip()}|{ap_role.strip().lower()}"
            if key not in existing_keys:
                storage.insert_job_matches(
                    [
                        {
                            "company_name": company_name,
                            "company_description": "",
                            "role_title": ap_role.strip(),
                            "location": "",
                            "url": "",
                            "priority": "",
                            "status": ap_status,
                            "date_found": ap_date.strftime("%Y-%m-%d"),
                        }
                    ]
                )
            storage.update_job_status(company_name, ap_role.strip(), ap_status)
            st.session_state[state.AP_SHOW_ADD_APPLIED] = False
            load_data.clear()
            st.rerun()

_applied_col_config = {
    "Status": st.column_config.SelectboxColumn(
        "Status", options=APPLIED_STATUS_OPTIONS, width="small"
    ),
    "Notes": st.column_config.TextColumn("Notes", width="large"),
    "\U0001f5d1\ufe0f": st.column_config.CheckboxColumn("\U0001f5d1\ufe0f", width="small"),
}


def _persist_tracker(original_df, edited_df):
    changed = False
    for idx in edited_df.index:
        if idx not in original_df.index:
            continue
        company = original_df.loc[idx, "Company"]
        if edited_df.loc[idx, "\U0001f5d1\ufe0f"]:
            storage.delete_tracker_entry(company)
            changed = True
            continue
        old_s = original_df.loc[idx, "Status"]
        new_s = edited_df.loc[idx, "Status"] or ""
        new_r = edited_df.loc[idx, "Role"] or ""
        new_n = edited_df.loc[idx, "Notes"] or ""
        if (
            old_s != new_s
            or (original_df.loc[idx, "Role"] or "") != new_r
            or (original_df.loc[idx, "Notes"] or "") != new_n
        ):
            storage.upsert_tracker_status(company, new_s, new_r, new_n)
            changed = True
    return changed


if _applied_tracker.empty:
    st.caption("No applications yet.")
else:
    _applied_display = _applied_tracker.copy()
    _applied_display["\U0001f5d1\ufe0f"] = False
    edited = st.data_editor(
        _applied_display,
        column_config=_applied_col_config,
        hide_index=True,
        use_container_width=True,
        disabled=[],
        key=state.AP_APPLIED_EDITOR,
    )
    if _persist_tracker(_applied_tracker, edited):
        st.rerun()

# Activity Log -------------------------------------------------------------
st.divider()
st.subheader("Activity Log")

if st.button("+ Add Entry", key=state.AP_ADD_LOG_BTN):
    st.session_state[state.AP_SHOW_ADD_LOG] = not st.session_state.get(state.AP_SHOW_ADD_LOG, False)

if st.session_state.get(state.AP_SHOW_ADD_LOG):
    with st.form("add_activity_log_form"):
        al_company = st.selectbox(
            "Company *", [""] + df_startups["Company Name"].tolist(), key=state.AL_COMPANY
        )
        al_new = st.text_input("Or enter new company name", key=state.AL_NEW)
        al_role = st.text_input("Role Title", key=state.AL_ROLE)
        al_type = st.selectbox("Activity Type *", ACTIVITY_TYPES, key=state.AL_TYPE)
        al_contact = st.text_input("Contact Name", key=state.AL_CONTACT)
        al_contact_title = st.text_input("Contact Title", key=state.AL_CONTACT_TITLE)
        al_email = st.text_input("Contact Email", key=state.AL_EMAIL)
        al_date = st.date_input("Date *", value=datetime.now(), key=state.AL_DATE)
        al_followup = st.date_input("Follow-up Date (optional)", value=None, key=state.AL_FOLLOWUP)
        al_notes = st.text_area("Notes", key=state.AL_NOTES)
        al_submit = st.form_submit_button("Add Entry")
    if al_submit:
        company_name = al_new.strip() if al_new.strip() else al_company
        if not company_name:
            st.error("Company is required.")
        else:
            storage.insert_activity(
                {
                    "company_name": company_name,
                    "role_title": al_role.strip(),
                    "activity_type": al_type,
                    "contact_name": al_contact.strip(),
                    "contact_title": al_contact_title.strip(),
                    "contact_email": al_email.strip(),
                    "date": al_date.strftime("%Y-%m-%d"),
                    "follow_up_date": al_followup.strftime("%Y-%m-%d") if al_followup else "",
                    "notes": al_notes.strip(),
                }
            )
            ts = storage.get_tracker_status(company_name)
            if not ts:
                storage.upsert_tracker_status(company_name, "In Progress", al_role.strip(), "")
            st.session_state[state.AP_SHOW_ADD_LOG] = False
            st.rerun()

if _active_tracker.empty:
    st.caption("No activities logged yet. Click '+ Add Entry' to start tracking.")
else:
    _tracker_col_config = {
        "Status": st.column_config.SelectboxColumn(
            "Status", options=TRACKER_STATUS_OPTIONS, width="small"
        ),
        "Notes": st.column_config.TextColumn("Notes", width="large"),
        "\U0001f5d1\ufe0f": st.column_config.CheckboxColumn("\U0001f5d1\ufe0f", width="small"),
    }
    st.caption(f"{len(_active_tracker)} active application(s)")
    _active_display = _active_tracker.copy()
    _active_display["\U0001f5d1\ufe0f"] = False
    edited = st.data_editor(
        _active_display,
        column_config=_tracker_col_config,
        hide_index=True,
        use_container_width=True,
        disabled=[],
        key=state.AP_ACTIVE_EDITOR,
    )
    if _persist_tracker(_active_tracker, edited):
        st.rerun()

# Rejected -----------------------------------------------------------------
st.divider()
_total_rejected = len(_rejected_tracker)
with st.expander(f"Rejected ({_total_rejected})"):
    if _total_rejected == 0:
        st.caption("No rejected entries.")
    else:
        _rej_display = _rejected_tracker.copy()
        _rej_display["\U0001f5d1\ufe0f"] = False
        edited = st.data_editor(
            _rej_display,
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    "Status", options=TRACKER_STATUS_OPTIONS, width="small"
                ),
                "\U0001f5d1\ufe0f": st.column_config.CheckboxColumn(
                    "\U0001f5d1\ufe0f", width="small"
                ),
            },
            hide_index=True,
            use_container_width=True,
            disabled=[],
            key=state.AP_REJECTED_EDITOR,
        )
        if _persist_tracker(_rejected_tracker, edited):
            st.rerun()
