---
paths:
  - "app.py"
  - "web/**"
  - "startup_radar/web/**"
---

# Streamlit dashboard rules

- **Must:** every DB read in the dashboard is wrapped in `@st.cache_data(ttl=60)` (or shorter for write-heavy views). See `app.py:59 load_data()`.
- **Must:** session-state keys are defined as module-level constants. No inline string literals like `key="ap_company"` (collision noted at `app.py:702`).
- **Never:** introduce a `web/components/` directory until ≥3 reuses exist. Premature DRY in Streamlit creates rerun-state bugs nastier than copy-paste (`docs/CRITIQUE_APPENDIX.md` §7).
- **Never:** call HTTP/network from inside a Streamlit page render. Fetch in pipeline, render from DB.
- **Must:** long-running operations (>500ms) use `st.spinner(...)`.
- **Never:** mutate global state inside a `@st.cache_data` function. Return a new value.
- **Must:** when adding a multi-page app, follow Streamlit's `pages/` convention with the `N_name.py` numeric prefix.
- **Must:** any new page documents which session-state keys it reads/writes at the top of the file.
- **Note:** Streamlit native multi-page has known gotchas with shared session state across pages — explicit handoff via constants only.
