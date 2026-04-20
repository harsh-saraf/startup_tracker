"""Cached DB wrappers. Every page imports reads through here, so the
``@st.cache_data(ttl=60)`` invariant from ``.claude/rules/dashboard.md``
bullet 1 stays in one place. The underlying ``Storage`` handle is a
``@st.cache_resource`` singleton — one ``SqliteStorage`` per Streamlit
process, shared across reruns without re-running the migrator.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from startup_radar.config import load_config
from startup_radar.storage import Storage, load_storage


@st.cache_resource
def get_storage() -> Storage:
    """One Storage instance per Streamlit process. Runs migrations on first
    call and stays hot across reruns."""
    return load_storage(load_config())


@st.cache_data(ttl=60)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(startups_df, jobs_df) — the dashboard's bread-and-butter read."""
    s = get_storage()
    return s.get_all_startups(), s.get_all_job_matches()


@st.cache_data(ttl=60)
def overdue_followups(today_iso: str) -> pd.DataFrame:
    return get_storage().get_overdue_followups(today_iso)


@st.cache_data(ttl=60)
def tracker_statuses() -> dict:
    return get_storage().get_all_tracker_statuses()


@st.cache_data(ttl=60)
def connections_count() -> int:
    return get_storage().get_connections_count()
