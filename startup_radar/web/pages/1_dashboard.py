"""Dashboard — top-level KPIs, today's companies, today's job matches,
follow-up reminders.

Session-state: none read/written (read-only view).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from startup_radar.config import load_config
from startup_radar.web.cache import load_data, overdue_followups, tracker_statuses

cfg = load_config()
TODAY = datetime.now().strftime("%Y-%m-%d")
# repo root: pages/1_dashboard.py -> pages -> web -> startup_radar -> repo
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent

df_startups, df_jobs = load_data()

st.title("Startup Radar")
user_name = cfg.user.name
if user_name:
    st.caption(f"Welcome back, {user_name}")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Companies Tracked", len(df_startups))
col2.metric("Job Matches", len(df_jobs))
interested = len(df_startups[df_startups["Status"].str.lower() == "interested"])
col3.metric("Interested", interested)
wishlisted = len(df_startups[df_startups["Status"].str.lower() == "wishlist"])
col4.metric("Wishlist", wishlisted)
_tracker_statuses = tracker_statuses()
applied_count = len([v for v in _tracker_statuses.values() if v["status"] == "Applied"])
applied_count += len(df_startups[df_startups["Status"].str.lower() == "applied"])
col5.metric("Applied", applied_count)

_overdue = overdue_followups(TODAY)
if not _overdue.empty:
    st.divider()
    st.subheader(f"Follow-ups Due ({len(_overdue)})")
    for _, row in _overdue.iterrows():
        _is_overdue = row["follow_up_date"] < TODAY
        _icon = "\U0001f534" if _is_overdue else "\U0001f7e1"
        _contact = f" \u2014 {row['contact_name']}" if row.get("contact_name") else ""
        _role = f" ({row['role_title']})" if row.get("role_title") else ""
        st.markdown(
            f"{_icon} **{row['company_name']}**{_role}{_contact}  \n"
            f"Due: {row['follow_up_date']} \u00b7 {row.get('notes', '')}"
        )

st.divider()

st.subheader("Today's Companies")
todays_companies = df_startups[df_startups["Date Found"] == TODAY]
if todays_companies.empty:
    _log_file = PROJECT_DIR / "logs" / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    _reason = "No new companies matched filters today."
    if _log_file.exists():
        _log_text = _log_file.read_text(encoding="utf-8", errors="replace")
        if "No new emails found" in _log_text:
            _reason = "No new funding newsletter emails received today."
        elif "all duplicates" in _log_text.lower():
            _reason = "Companies were found but all were already in the database."
    st.caption(_reason)
else:
    for _, row in todays_companies.iterrows():
        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
        c1.markdown(f"**{row['Company Name']}**")
        desc = row["Description"]
        c2.write(desc[:80] + "..." if len(str(desc)) > 80 else desc)
        c3.write(row["Funding Stage"])
        c4.write(row["Amount Raised"])

st.divider()

st.subheader("Today's Job Matches")
todays_jobs = df_jobs[df_jobs["Date Found"] == TODAY]
if todays_jobs.empty:
    st.caption("No job matches found today.")
else:
    for _, row in todays_jobs.iterrows():
        c1, c2, c3, c4 = st.columns([2, 3, 2, 1])
        c1.markdown(f"**{row.get('Company', '')}**")
        c2.write(row.get("Role", ""))
        c3.write(row.get("Location", ""))
        priority = row.get("Priority", "")
        if priority == "High":
            c4.markdown(":red[**High**]")
        elif priority == "Medium":
            c4.markdown(":orange[**Medium**]")
        else:
            c4.write(priority)
