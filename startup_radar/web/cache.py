"""Cached DB wrappers. Every page imports reads through here, not
``database`` directly, so the ``@st.cache_data(ttl=60)`` invariant from
``.claude/rules/dashboard.md`` bullet 1 stays in one place. Writes still
go through ``database`` — caching writes would be wrong.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import database


@st.cache_data(ttl=60)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(startups_df, jobs_df) — the dashboard's bread-and-butter read."""
    return database.get_all_startups(), database.get_all_job_matches()


@st.cache_data(ttl=60)
def overdue_followups(today_iso: str) -> pd.DataFrame:
    return database.get_overdue_followups(today_iso)


@st.cache_data(ttl=60)
def tracker_statuses() -> dict:
    return database.get_all_tracker_statuses()


@st.cache_data(ttl=60)
def connections_count() -> int:
    return database.get_connections_count()
