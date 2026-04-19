# Phase 9 Execution Plan — Decompose `app.py` into `startup_radar/web/pages/` + cache wrappers

> Kill the 1,299-line single-file dashboard. Move each of the five pages to `startup_radar/web/pages/N_name.py` (Streamlit native multi-page), lift the cached DB reader and session-state keys into shared modules, and fix two latent bugs along the way (`from main import run` — dead since Phase 4 — and the duplicate `key=` collisions called out in `docs/CRITIQUE_APPENDIX.md` §7). Closes row 11 in `docs/PRODUCTION_REFACTOR_PLAN.md` §0a and unblocks the `streamlit.testing.v1.AppTest` smoke tests deferred from Phase 8 (now in-scope for Phase 10 or Phase 13).

## Phase summary

- **Relocate the dashboard** from repo-root `app.py` (1,299 LOC) to `startup_radar/web/`:
  - `startup_radar/web/app.py` — thin shell (~60 lines): page-config, config load, `database.set_db_path` + `init_db`, sidebar render, no page logic.
  - `startup_radar/web/pages/1_dashboard.py` (today 217–293, ~77 LOC)
  - `startup_radar/web/pages/2_companies.py` (298–486, ~189 LOC)
  - `startup_radar/web/pages/3_jobs.py` (492–681, ~190 LOC)
  - `startup_radar/web/pages/4_deepdive.py` (687–965, ~279 LOC)
  - `startup_radar/web/pages/5_tracker.py` (971–1299, ~329 LOC)
  - Streamlit discovers these by convention; the numeric prefix drives sidebar order, the stem (minus prefix + underscore) becomes the nav label. `1_dashboard.py` → "dashboard"; we relabel via `st.sidebar` titles inside each page if the default casing looks wrong.
- **Extract shared helpers** — two small sibling modules, no `components/` yet:
  - `startup_radar/web/cache.py` — single `@st.cache_data(ttl=60)` wrapper around `database.get_all_startups()` + `database.get_all_job_matches()` (today `app.py:60-62`) plus re-exports of the frequently-hit `database.get_connections_count`, `get_overdue_followups`, `get_all_tracker_statuses`. Every page imports from here; none re-wrap.
  - `startup_radar/web/state.py` — module-level string constants for the ~25 `st.session_state[...]` keys currently strewn as literals. Addresses `docs/CRITIQUE_APPENDIX.md` §7 collision at `app.py:702` (`dd_name_input` / `ac_name_input` and the `co_lookup` / `dd_lookup` twins).
- **Sidebar stays in `web/app.py`** — the LinkedIn CSV uploader (today `app.py:167-199`) and "Run pipeline now" button (`app.py:158-164`) are page-agnostic, so they live in the shell and render on every page. Uses Streamlit's pattern: put sidebar code at module top before any page swaps in.
- **Fix `from main import run`** (`app.py:160`) — `main.py` was deleted in Phase 4; this import currently raises `ModuleNotFoundError` the moment a user clicks "Run pipeline now". Replace with a direct call to `startup_radar.cli._pipeline()` (private but stable; if we're uncomfortable with the leading underscore, promote `_pipeline` → `pipeline` in the same commit).
- **Fix `from duckduckgo_search import DDGS`** hot-import (`app.py:74`) — this gets re-executed on every rerun of the Companies or DeepDive page. Move to module-import at the top of `web/lookup.py` (new), guarded by a `try/except ImportError` so the optional dep can fail loudly once at startup instead of silently per-click.
- **Update the `serve` CLI** — `startup_radar/cli.py:210` currently points `streamlit run` at `repo_root / "app.py"`. Retarget to `startup_radar/web/app.py`. Same `--server.port` + `--` passthrough semantics.
- **Relocate `connections.py`** — the 46-LOC `connections.py` at repo root is dashboard-only (tier-1/tier-2 helpers around LinkedIn CSV import). Moves to `startup_radar/web/connections.py`. Its two callers (`app.py`, `database.py`) update their imports. Zero behavior change.
- **Leave `database.py` alone** — it's Phase 10's concern (`PRAGMA user_version` + `Storage` class). Pages keep importing from the top-level module.
- **Session-state audit** — every page header gets a docstring listing the session-state keys it reads and writes (dashboard.md rule 7). The audit lives in the file, not in docs, so the invariant travels with the code.
- **Docs**: `README.md` "Development" section gains a "Dashboard layout" subsection; `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 11 → ✅; `.claude/CLAUDE.md` repo-layout tree updates (`app.py` row → `startup_radar/web/…`; "multi-page split in Phase 11" → "multi-page split DONE Phase 9") and Gotchas gains one line on the sidebar-lives-in-web/app.py invariant.
- **Harness**: no `.claude/settings.json` changes needed — `Bash(uv run *)` already covers the `uv run streamlit run …` invocation used by `startup-radar serve`, and no new deps are added.

## Out of scope (deferred)

| Item | Deferred to | Why |
|---|---|---|
| `streamlit.testing.v1.AppTest` per-page smoke tests | Phase 10 pick-up | Testing rule 7 requires `AppTest`; wiring is trivial *after* the split, but the cassette work done in Phase 8 is the proof of the per-source contract. Adding five AppTest files in the same PR risks destabilizing the split. One AppTest sanity test that loads `web/app.py` without exception is in-scope here (§3.5 below). |
| `web/components/` (shared cards / pills / intro-list widgets) | Not before ≥3 reuses | Both `docs/CRITIQUE_APPENDIX.md` §7 and `.claude/rules/dashboard.md` bullet 3 forbid premature DRY — rerun-state bugs from shared components are worse than copy-paste. Revisit after Phase 10. |
| `web/cache.py` with fine-grained per-query caching | Phase 10 | Today `load_data()` returns both dataframes in one call; splitting caches is a micro-opt that only matters once `database.py` becomes `Storage` and per-query invalidation is possible. |
| Replace `subprocess.Popen` DeepDive runner (`app.py:804-816`) with `asyncio` or `concurrent.futures` | never (single-user tool) | Subprocess is crude but robust — it crosses the Streamlit rerun boundary cleanly and lets us track a detached `.docx` build via filesystem polling. An in-process runner would hang the UI thread. |
| Rebuild the DeepDive progress bar as a real-time log tail | never | Cosmetic; the heuristic timer-based progress is good enough and doesn't block on subprocess stdio. |
| Rename `database.py` → `startup_radar/storage/sqlite.py` | Phase 10 | Storage refactor is the natural pairing; doing it here would double the diff size and merge risk. |
| Convert `_lookup_company` (DuckDuckGo) to use the project-wide httpx client | Phase 13 | `httpx` migration is the Tier 2 HTTP normalization work; not today. |
| Dashboard auth / multi-user session isolation | never | Out of scope per `docs/CRITIQUE_APPENDIX.md` §12. |
| Dark-mode theming / CSS injection | never | Streamlit's built-in light/dark selector is sufficient; custom CSS is a maintenance tax for one user. |
| MkDocs page documenting each Streamlit page | Phase 15 (if ever) | Each page's module docstring is the documentation; duplicating it in MkDocs is busywork. |
| Extract the "Add Company" form out of Companies + DeepDive (currently duplicated, `app.py:306-353` + `698-745`) | Next time either copy changes | Candidate for `components/` once a third reuse appears. Leave as two near-identical blocks with a `# TODO(phase-10): consolidate if a 3rd caller shows up` comment in each. |

## Effort estimate

- **2 engineering days** per `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 11. This is one of the rare phases where the item estimate looks right on first reading — the work is mechanical cut/paste plus two small module extractions, no new dep, no CI surface area.
- Critical path: sidebar + cache-wrapper correctness. Streamlit's native multi-page mode re-executes the top-level `web/app.py` on every page navigation, so the sidebar and data-load must be idempotent and cheap. Verify by clicking through all five pages and confirming `load_data` is cached (time it with `time.perf_counter()` in a throwaway debug print, delete before commit).
- Secondary: the `main.py` import fix. Easy to miss because the branch is behind a button click. Manual smoke test: `uv run startup-radar serve`, click "Run pipeline now", confirm no `ModuleNotFoundError` and the pipeline actually runs.
- Tertiary: update `startup-radar serve` to point at the new shell and re-run `uv sync --all-extras` if the entry-point binding needs a refresh (it shouldn't — `cli.py` is not being renamed, only its `app_path` literal).
- Tag at end: `phase-9`.

## Prerequisites

- ✅ Phase 8 (commit `2a87c5f`, tag `phase-8`). vcrpy cassettes + CI gate in place so we can tell if the split broke a source contract.
- ✅ `make ci` green at start. Working tree clean.
- ✅ `streamlit>=1.30` already in `pyproject.toml` (native multi-page apps require ≥1.10; we're well past).
- No new runtime deps. No new dev deps. No new GitHub secrets. No new MCP servers.
- ⚠️ Heads-up: `.claude/CLAUDE.md` currently says "multi-page split in Phase 11". This phase is `phase-9` (matching the tag sequence and §0a row numbering). The CLAUDE.md copy gets corrected as part of this phase's doc updates.

---

## 1. Files to change

| Path | Action | Notes |
|---|---|---|
| `app.py` | **delete** | Contents redistributed across `startup_radar/web/`. Keep the git history visible via `git mv` for the shell (`app.py` → `startup_radar/web/app.py`) so `git log --follow` works. |
| `startup_radar/web/__init__.py` | **create** | Empty. |
| `startup_radar/web/app.py` | **create** (via `git mv` of `app.py`) | Shell: ~60 lines. `st.set_page_config`, config load, DB init, sidebar. Drops all page conditionals. |
| `startup_radar/web/pages/__init__.py` | **create** | Empty. Required for `AppTest` imports in Phase 10; Streamlit itself does not need it. |
| `startup_radar/web/pages/1_dashboard.py` | **create** | Ex-`app.py:217-293`. Imports cache + state from siblings. |
| `startup_radar/web/pages/2_companies.py` | **create** | Ex-`app.py:298-486`. |
| `startup_radar/web/pages/3_jobs.py` | **create** | Ex-`app.py:492-681`. |
| `startup_radar/web/pages/4_deepdive.py` | **create** | Ex-`app.py:687-965`. |
| `startup_radar/web/pages/5_tracker.py` | **create** | Ex-`app.py:971-1299`. |
| `startup_radar/web/cache.py` | **create** | `load_data()` + re-exports. ~30 lines. |
| `startup_radar/web/state.py` | **create** | Session-state key constants. ~40 lines. |
| `startup_radar/web/lookup.py` | **create** | `_lookup_company` (ex-`app.py:72-97`) with hoisted DDG import. ~30 lines. |
| `startup_radar/web/connections.py` | **create** (via `git mv` of `connections.py`) | No content change; just the move. |
| `connections.py` | **delete** (via `git mv`) | Ditto. Callers in `app.py` (gone) and `database.py` update. |
| `database.py` | edit (imports only) | `from connections import …` → `from startup_radar.web.connections import …`. One or two lines. |
| `startup_radar/cli.py` | edit | `app_path = repo_root / "app.py"` → `app_path = repo_root / "startup_radar" / "web" / "app.py"`. Also: promote `_pipeline()` → `pipeline()` (§2.5) so `web/app.py` can call it without a leading-underscore import. |
| `tests/unit/test_web_smoke.py` | **create** | One test: `AppTest.from_file("startup_radar/web/app.py").run()` exits without exception. ~20 lines. Protects against the class of "import fixed pages/dashboard.py breaks because state.KEY_X undefined" regressions. |
| `Makefile` | edit | `serve` target — no change needed (`uv run startup-radar serve` is indirection-safe). Verify. |
| `README.md` | edit | "Development" gets a "Dashboard layout" subsection pointing at `startup_radar/web/pages/`. |
| `docs/PRODUCTION_REFACTOR_PLAN.md` | edit | §0a row 11 → ✅ with tag + commit ref. §3.1 target-layout tree gets a tick mark on `web/`. |
| `.claude/CLAUDE.md` | edit | Repo-layout tree: replace `app.py` row with `startup_radar/web/…`; replace the "multi-page split in Phase 11" annotation; add a Gotcha about sidebar living in the shell. |
| `docs/plans/phase-9.md` | **create** | This document. |

### Files explicitly NOT to touch

- `database.py` module-level logic (only the two `from connections …` import lines change).
- `startup_radar/sources/*`, `parsing/*`, `filters.py`, `research/deepdive.py` — none of the Phase 3/4/5 package code touches the dashboard.
- `sinks/google_sheets.py` — unaffected.
- `.github/workflows/*.yml` — CI gate from Phase 8 exercises the new layout on first PR push; no workflow edits needed.
- `config.yaml`, `config.example.yaml` — no shape changes.
- `tests/integration/*` — source tests are independent of the dashboard.

---

## 2. New/changed file shapes

### 2.1 `startup_radar/web/app.py` — the shell

```python
"""Startup Radar — Streamlit dashboard shell.

Streamlit native multi-page app. Pages auto-discovered from
``startup_radar/web/pages/``. This module renders the page-config,
the sidebar, and the shared DB init — nothing page-specific.

Session-state keys read/written here:
  - ``li_csv_upload``   (LinkedIn CSV uploader file)
  - none else; page-specific keys live in their respective files.
"""

from __future__ import annotations

import csv as _csv
from datetime import datetime
from pathlib import Path

import streamlit as st

import database
from startup_radar.config import load_config
from startup_radar.web import cache, state  # noqa: F401  # imported for side-effect validation

st.set_page_config(page_title="Startup Radar", page_icon=":satellite:", layout="wide")

try:
    cfg = load_config()
    sqlite_path = cfg.output.sqlite.path if cfg.output.sqlite.enabled else None
    if sqlite_path:
        database.set_db_path(sqlite_path)
except Exception as e:
    st.error(f"Config error: {e}")
    st.stop()

database.init_db()

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent  # repo root
REPORTS_DIR = PROJECT_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# --- sidebar (shared across every page) -----------------------------------

if st.sidebar.button("Run pipeline now"):
    with st.spinner("Running..."):
        from startup_radar.cli import pipeline  # promoted from _pipeline in this phase
        pipeline()
    st.success("Done")
    st.rerun()

st.sidebar.divider()
st.sidebar.markdown("**LinkedIn Connections**")

_li_last = database.get_connections_last_uploaded()
_li_count = database.get_connections_count()
if _li_last:
    try:
        _li_dt = datetime.fromisoformat(_li_last)
        _li_days_ago = (datetime.now() - _li_dt).days
        st.sidebar.caption(
            f"{_li_count} connections \u00b7 Updated {_li_dt.strftime('%b %d, %Y')}"
        )
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
    _content = _li_file.getvalue().decode("utf-8", errors="replace")
    _lines = _content.splitlines()
    _data_start = next(
        (i for i, ln in enumerate(_lines) if "First Name" in ln and "Last Name" in ln),
        0,
    )
    _rows = [
        r for r in _csv.DictReader(_lines[_data_start:])
        if r.get("First Name") or r.get("Last Name")
    ]
    _imported = database.import_connections(_rows)
    st.sidebar.success(f"Imported {_imported} connections")
    st.rerun()
```

Gotchas:
- The sidebar renders from this shell, not from each page. Streamlit native multi-page re-runs *both* the shell and the active page on every interaction, so sidebar code here appears on every page automatically. Do not duplicate into the pages.
- `PROJECT_DIR` — two `.parent` hops from `startup_radar/web/app.py` to repo root.  Pages needing `REPORTS_DIR` import it from here (`from startup_radar.web.app import REPORTS_DIR`) OR we pull it into a tiny `web/paths.py` if mypy complains about cross-page top-level imports. Decide in §3.3.

### 2.2 `startup_radar/web/state.py`

```python
"""Session-state key constants. Import these; never use string literals.

Enforces `.claude/rules/dashboard.md` bullet 2. The explicit namespace
prefixes (``co_``, ``dd_``, ``ap_``, etc.) mirror the page they belong to
and defuse the collision called out at the former ``app.py:702``.
"""

from __future__ import annotations

# Sidebar
LI_CSV_UPLOAD = "li_csv_upload"

# Page 2 — Companies
CO_SHOW_ADD = "show_add_company"
CO_LOOKUP = "co_lookup"
CO_LOOKUP_VERSION = "co_lookup_v"
CO_SEARCH = "co_search"
CO_NAME_INPUT = "ac_name_input"
CO_LOOKUP_BUTTON = "co_lookup_btn"

# Page 3 — Jobs
JOB_SHOW_ADD = "show_add_role"
JOB_SEARCH = "job_search"

# Page 4 — DeepDive
DD_SHOW_ADD = "show_add_company_dd"
DD_LOOKUP = "dd_lookup"
DD_LOOKUP_VERSION = "dd_lookup_v"
DD_NAME_INPUT = "dd_name_input"           # <- was colliding with CO_NAME_INPUT at app.py:702
DD_LOOKUP_BUTTON = "dd_lookup_btn"
DD_SELECT = "deepdive_select"
DD_GENERATING = "generating"
DD_GEN_PROC = "gen_proc"
DD_GEN_START = "gen_start"
DD_SHOW_WARM_INTROS = "show_warm_intros"

# Page 5 — Tracker
AP_SHOW_ADD_ACTIVITY = "show_add_activity"
AP_COMPANY = "ap_company"
# …add more as the tracker page is ported.

ALL_KEYS: tuple[str, ...] = tuple(
    v for k, v in globals().items() if k.isupper() and isinstance(v, str)
)


def assert_no_collisions() -> None:
    """Dev-mode guard — catches two constants pointing at the same string."""
    if len(ALL_KEYS) != len(set(ALL_KEYS)):
        dupes = [k for k in set(ALL_KEYS) if ALL_KEYS.count(k) > 1]
        raise AssertionError(f"session-state key collision: {dupes}")


assert_no_collisions()  # runs at import time; fails loud on dev mistake
```

### 2.3 `startup_radar/web/cache.py`

```python
"""Cached DB wrappers. Every page imports from here, not ``database`` directly,
for reads that participate in the Streamlit render loop. Writes still go
through ``database`` — caching writes would be wrong.
"""

from __future__ import annotations

import streamlit as st

import database


@st.cache_data(ttl=60)
def load_data() -> tuple:
    """(startups_df, jobs_df) — the dashboard's bread-and-butter read."""
    return database.get_all_startups(), database.get_all_job_matches()


@st.cache_data(ttl=60)
def overdue_followups(today_iso: str):
    return database.get_overdue_followups(today_iso)


@st.cache_data(ttl=60)
def tracker_statuses() -> dict:
    return database.get_all_tracker_statuses()


@st.cache_data(ttl=60)
def connections_count() -> int:
    return database.get_connections_count()
```

Notes:
- TTL=60s matches the existing invariant at the former `app.py:60`. Writes that must invalidate immediately (e.g. "Add Company") call `load_data.clear()` after insert — pages add one line each.
- We do NOT cache the full connection dataframe (`database.get_connections`) — today's sidebar logic reads `get_connections_count` + `get_connections_last_uploaded` which are cheap, and the per-company search happens inside a `with st.spinner(...)` block that users expect to be live.

### 2.4 `startup_radar/web/lookup.py`

```python
"""DuckDuckGo company lookup. Hoisted out of the Companies/DeepDive pages so
the import happens once at module load instead of on every rerun.
"""

from __future__ import annotations

import logging
import re

try:
    from duckduckgo_search import DDGS
    _DDG_AVAILABLE = True
except ImportError:
    _DDG_AVAILABLE = False

log = logging.getLogger(__name__)


def lookup_company(name: str) -> dict:
    if not _DDG_AVAILABLE:
        return {}
    try:
        results = list(DDGS().text(f"{name} startup funding raised", max_results=5))
    except Exception as e:
        log.warning("lookup.failed", extra={"company": name, "err": str(e)})
        return {}
    if not results:
        return {}
    snippets = " ".join(r.get("body", "") for r in results)
    info: dict = {}
    first_body = results[0].get("body", "")
    if first_body:
        info["description"] = first_body[:200].rstrip()
    amt = re.search(r"\$[\d,.]+\s*[BM]\b|\$[\d,.]+\s*(?:million|billion)", snippets, re.IGNORECASE)
    if amt:
        info["amount_raised"] = amt.group(0).strip()
    stage = re.search(r"Series\s+[A-F]\d?\+?|Pre-[Ss]eed|Seed", snippets)
    if stage:
        info["funding_stage"] = stage.group(0).strip()
    loc = re.search(
        r"(?:based in|headquartered in)\s+([^,.\n]+(?:,\s*[A-Za-z. ]+)?)",
        snippets,
        re.IGNORECASE,
    )
    if loc:
        info["location"] = loc.group(1).strip()
    return info
```

Observability rule compliance: replaces the bare `except` swallow with a `logger.warning("lookup.failed", ...)` structured record. Phase 13's structlog migration will pick this up for free.

### 2.5 `startup_radar/cli.py` diff

```diff
- def _pipeline() -> int:
+ def pipeline() -> int:
      """Run the discovery pipeline once.  Public API — called by
      ``startup_radar.web.app``'s ``Run pipeline now`` button and by the
      ``run`` CLI command.
      """
      …
@@
  def run(scheduled: bool = False) -> None:
      if not scheduled:
-         raise typer.Exit(code=_pipeline())
+         raise typer.Exit(code=pipeline())
      …
-     rc = _pipeline()
+     rc = pipeline()
@@
  def serve(port: int = 8501) -> None:
      repo_root = Path(__file__).resolve().parent.parent
-     app_path = repo_root / "app.py"
+     app_path = repo_root / "startup_radar" / "web" / "app.py"
      cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)]
      raise typer.Exit(code=subprocess.call(cmd))
```

One rename (`_pipeline` → `pipeline`), two call sites updated, one path literal changed. Nothing else in `cli.py` moves.

### 2.6 `startup_radar/web/pages/1_dashboard.py` (sketch)

```python
"""Dashboard — top-level KPIs + today's funding + today's jobs.

Session-state: none read/written (this page is read-only).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

import database
from startup_radar.config import load_config
from startup_radar.web.cache import load_data, overdue_followups, tracker_statuses

cfg = load_config()
TODAY = datetime.now().strftime("%Y-%m-%d")
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent  # repo root

df_startups, df_jobs = load_data()

st.title("Startup Radar")
if cfg.user.name:
    st.caption(f"Welcome back, {cfg.user.name}")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Companies Tracked", len(df_startups))
col2.metric("Job Matches", len(df_jobs))
col3.metric("Interested", len(df_startups[df_startups["Status"].str.lower() == "interested"]))
col4.metric("Wishlist", len(df_startups[df_startups["Status"].str.lower() == "wishlist"]))

_ts = tracker_statuses()
applied = len([v for v in _ts.values() if v["status"] == "Applied"])
applied += len(df_startups[df_startups["Status"].str.lower() == "applied"])
col5.metric("Applied", applied)

_overdue = overdue_followups(TODAY)
if not _overdue.empty:
    st.divider()
    st.subheader(f"Follow-ups Due ({len(_overdue)})")
    for _, row in _overdue.iterrows():
        …  # verbatim from app.py:240-248
```

Notes:
- Each page does its *own* `load_config()` + `load_data()` call. Streamlit caches both, so the second-page render hits the cache; no DB round-trip.
- `PROJECT_DIR` is redefined per page rather than imported from the shell — keeps pages standalone-testable under `AppTest`.
- The `from main import run` at `app.py:160` does NOT appear anywhere in page code — it lives in the shell, now pointing at `startup_radar.cli.pipeline`.

### 2.7 `tests/unit/test_web_smoke.py`

```python
"""Loads the dashboard shell under Streamlit's AppTest. Proves:
  1. The import graph is sound (no broken import, no collision in ``state.py``).
  2. The sidebar renders without touching the real DB (DB init is config-gated).
  3. Five discoverable pages exist.

Per ``.claude/rules/testing.md`` bullet 7.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_shell_loads_without_exception(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parent.parent.parent)
    at = AppTest.from_file("startup_radar/web/app.py", default_timeout=10)
    at.run()
    assert not at.exception, f"shell raised: {at.exception}"


def test_pages_discoverable() -> None:
    pages = sorted(
        p.stem for p in (
            Path(__file__).resolve().parent.parent.parent
            / "startup_radar" / "web" / "pages"
        ).glob("*.py") if not p.name.startswith("__")
    )
    assert pages == ["1_dashboard", "2_companies", "3_jobs", "4_deepdive", "5_tracker"]
```

One AppTest per page (five more tests) is deferred to Phase 10 pick-up. This is the minimum that catches "I broke the shell" regressions.

---

## 3. Execution order

1. **Branch**: stay on `refactor/v2` (we've been cutting phase tags off it since Phase 3). Working tree clean before starting.
2. **Create package skeleton** — `startup_radar/web/{__init__.py,pages/__init__.py}`, both empty. Commit separately so the `git mv` in step 3 has a target.
3. **`git mv`** — `app.py` → `startup_radar/web/app.py` and `connections.py` → `startup_radar/web/connections.py`. History-preserving.
4. **Strip the shell** — edit `startup_radar/web/app.py` down to ~60 lines per §2.1. The five page bodies are the diff-delete here.
5. **Extract siblings** — write `cache.py`, `state.py`, `lookup.py` per §2.2-2.4. Run `make lint` after each to catch typos.
6. **Split the pages** — create the five `pages/N_name.py` files, each lifting its section verbatim from the (pre-strip) `app.py`. Sanity rule: the first commit per page should be a near-identical paste; a *second* commit per page changes session-state literals to `state.*` constants. Two-step split is easier to review.
7. **Fix the pipeline import** — `startup_radar/cli.py` rename `_pipeline` → `pipeline`, update the button handler in `web/app.py` to match.
8. **Update `database.py`** — swap the two `from connections import …` import lines.
9. **Update `startup-radar serve`** — change `app_path` literal per §2.5. Test: `uv run startup-radar serve` launches at :8501.
10. **Manual QA pass** — click through all five pages, use the sidebar pipeline button, upload a fake LinkedIn CSV, trigger an "Add Company" on both Companies and DeepDive to confirm session-state doesn't collide. Expected time: 15 min.
11. **Write the smoke test** — `tests/unit/test_web_smoke.py` per §2.7.
12. **Run `make ci`** — must be green. Pay special attention to `mypy` on `web/app.py`'s `from startup_radar.cli import pipeline` circular-import risk (shell imports CLI; CLI shouldn't import web — verify).
13. **Docs pass** — update `README.md`, `docs/PRODUCTION_REFACTOR_PLAN.md` §0a, `.claude/CLAUDE.md` repo-layout + gotcha.
14. **Tag** — `git tag phase-9 && git push origin phase-9`. (User-driven per CLAUDE.md's "do not delegate commits" rule — this plan surfaces the tag, it doesn't push it.)

---

## 4. Rollback plan

Single-commit phase. If the shell breaks or Streamlit's multi-page discovery surprises us in ways not caught by the smoke test:

```bash
git revert <phase-9-commit-sha>     # produces a clean inverse commit
git tag -d phase-9                  # local only; tag hasn't been pushed yet if we catch it early
git push --delete origin phase-9    # only if the tag escaped
```

Because `git mv` was used, a revert cleanly restores `app.py` and `connections.py` at the repo root.

The `_pipeline` → `pipeline` rename is the one change that affects non-web callers (`cli.py`'s `run` command). A revert restores both. No migration needed mid-revert.

---

## 5. Exit criteria

- [ ] `app.py` at repo root no longer exists.
- [ ] `connections.py` at repo root no longer exists.
- [ ] `startup_radar/web/app.py` exists, ≤80 lines.
- [ ] `startup_radar/web/pages/{1_dashboard,2_companies,3_jobs,4_deepdive,5_tracker}.py` all exist.
- [ ] `startup_radar/web/{cache,state,lookup,connections}.py` all exist.
- [ ] No `from main import` anywhere in the codebase (grep confirms).
- [ ] No `st.session_state["..."]` string literal inside `startup_radar/web/pages/` (all go through `state.*`). `grep -rn 'st\.session_state\["' startup_radar/web/pages/` returns nothing.
- [ ] `uv run startup-radar serve` opens the dashboard at :8501; the five pages appear in the sidebar; "Run pipeline now" does not `ModuleNotFoundError`.
- [ ] `make ci` green. `tests/unit/test_web_smoke.py` passes.
- [ ] `streamlit run startup_radar/web/app.py` (the bare form) also works — our CLI wrapper is not load-bearing.
- [ ] `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 11 shows ✅ with the `phase-9` tag + commit ref.
- [ ] `.claude/CLAUDE.md` repo-layout tree updated; "Phase 11" stale references all corrected to "Phase 9".
- [ ] Tag `phase-9` pushed (by the user, not Claude).

---

## 6. Post-phase note

**Phase 10 (§0a row 12): `Storage` class + `PRAGMA user_version` migrator.** With the dashboard split, Phase 10 can safely refactor `database.py` → `startup_radar/storage/sqlite.py` behind a `Storage` protocol without simultaneously rewriting the 1,100-line callsite. The page modules and `cache.py` are the only callers; swapping the import is a one-line change per file.

**Also unlocked**: five per-page `AppTest`-backed tests that actually exercise render logic — defer but keep in mind for Phase 13 or a quiet afternoon.
