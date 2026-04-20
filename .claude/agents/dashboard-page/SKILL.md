---
name: dashboard-page
description: Use to scaffold a new Streamlit page or refactor a section of `app.py` into a discrete view.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# dashboard-page

## When to use
- User says "add a page for X" or "extract the Y section of app.py".
- A new dashboard view needs caching + state conventions applied correctly.

## Process
1. Read `.claude/rules/dashboard.md` for caching/state rules.
2. Read the relevant section of `app.py` (currently ~1100 LOC).
3. Either (a) add a section to `app.py` if multi-page is not yet introduced, or (b) create `web/pages/N_<name>.py` if `web/` exists.
4. Wrap every DB read in `@st.cache_data(ttl=60)`.
5. Define session-state keys as module-level constants at the top of the file.
6. Add a `streamlit.testing.v1.AppTest`-based smoke test under `tests/unit/test_pages.py`.

## Constraints
- Never introduce `web/components/` until ≥3 reuses exist.
- Never make HTTP calls inside the render function — fetch in pipeline, render from DB.
- Never use inline string literals for `key=` — always module-level constants.
