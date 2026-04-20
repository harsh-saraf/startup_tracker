"""Streamlit dashboard shell. Pages auto-discovered from
``startup_radar/web/pages/``. Owns page-config, config load, storage init,
and the shared sidebar — nothing page-specific.

Session-state keys read/written here: ``state.LI_CSV_UPLOAD`` (uploader).
"""

from __future__ import annotations

import csv as _csv
from datetime import datetime
from pathlib import Path

import streamlit as st

from startup_radar.config import load_config, secrets
from startup_radar.observability.logging import configure_logging
from startup_radar.web import state
from startup_radar.web.cache import get_storage

configure_logging(json=secrets().log_json)

st.set_page_config(page_title="Startup Radar", page_icon=":satellite:", layout="wide")

try:
    cfg = load_config()
except Exception as e:
    st.error(f"Config error: {e}")
    st.stop()

storage = get_storage()

PROJECT_DIR = Path(__file__).resolve().parents[2]  # startup_radar/web/app.py -> repo
REPORTS_DIR = PROJECT_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# --- sidebar (rendered on every page) --------------------------------------

if st.sidebar.button("Run pipeline now"):
    with st.spinner("Running..."):
        from startup_radar.cli import pipeline

        pipeline()
    st.success("Done")
    st.rerun()

st.sidebar.divider()
st.sidebar.markdown("**LinkedIn Connections**")

_li_last = storage.get_connections_last_uploaded()
_li_count = storage.get_connections_count()
if _li_last:
    try:
        _li_dt = datetime.fromisoformat(_li_last)
        _li_days_ago = (datetime.now() - _li_dt).days
        st.sidebar.caption(f"{_li_count} connections \u00b7 Updated {_li_dt.strftime('%b %d, %Y')}")
        if _li_days_ago > 30:
            st.sidebar.warning(
                "Connections may be stale \u2014 consider re-exporting from LinkedIn"
            )
    except Exception:
        st.sidebar.caption(f"{_li_count} connections")
else:
    st.sidebar.caption("Not yet uploaded")

_li_file = st.sidebar.file_uploader(
    "Upload CSV", type="csv", key=state.LI_CSV_UPLOAD, label_visibility="collapsed"
)
if _li_file is not None:
    _lines = _li_file.getvalue().decode("utf-8", errors="replace").splitlines()
    _data_start = next(
        (i for i, ln in enumerate(_lines) if "First Name" in ln and "Last Name" in ln), 0
    )
    _rows = [
        r
        for r in _csv.DictReader(_lines[_data_start:])
        if r.get("First Name") or r.get("Last Name")
    ]
    st.sidebar.success(f"Imported {storage.import_connections(_rows)} connections")
    st.rerun()
