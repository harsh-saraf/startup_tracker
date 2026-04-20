# Phase 10 Execution Plan — `Storage` class + `PRAGMA user_version` migrator

> Retire repo-root `database.py` (732 LOC, 33 free functions) in favor of `startup_radar/storage/sqlite.py` — a thin `SqliteStorage` class with a single process-wide connection and a homegrown `PRAGMA user_version` migrator. Closes row 12 in `docs/PRODUCTION_REFACTOR_PLAN.md` §0a and aligns the repo with `.claude/rules/storage.md` bullet 3. **Explicitly NOT alembic** per `docs/CRITIQUE_APPENDIX.md` §4.

## Phase summary

- **Relocate the DB layer** from repo-root `database.py` into a new subpackage:
  - `startup_radar/storage/__init__.py` — re-exports `Storage` (protocol) and `load_storage()` (factory).
  - `startup_radar/storage/base.py` — `Storage` protocol per `docs/PRODUCTION_REFACTOR_PLAN.md` §3.1. Today only one implementation (`SqliteStorage`); protocol earns its keep by making `tests/unit/` fakeable without touching disk.
  - `startup_radar/storage/sqlite.py` — `SqliteStorage` class wrapping a single `sqlite3.Connection`, WAL, `check_same_thread=False`. All 33 functions become methods. `_connect()`-per-call goes away.
  - `startup_radar/storage/migrator.py` — `apply_pending(conn, migrations_dir) -> list[int]`. Reads `PRAGMA user_version`, walks `*.sql` in lexical order, applies any above current version inside a single `with conn:` transaction, bumps `user_version`.
  - `startup_radar/storage/migrations/0001_initial.sql` — verbatim extraction of the current `database.init_db()` `executescript` body (lines 29-117). Creates every table + index the app expects today. This is the baseline; DBs that predate Phase 10 are silently upgraded to `user_version=1` because `CREATE TABLE IF NOT EXISTS` is idempotent — the migrator treats "pre-versioned" (`user_version=0`) as "no migrations applied" and runs `0001` safely over an already-populated schema.
- **Introduce `load_storage(cfg) -> Storage`** — single entry point, reads `cfg.output.sqlite.path`, instantiates `SqliteStorage(Path(path))`, calls `.migrate_to_latest()`, returns the instance. Every caller goes through this (CLI, web shell, tests).
- **One connection per process, not per call.** `database.py:20-23` opens a fresh connection on every function call — harmless for single-user SQLite perf (see `.claude/rules/storage.md` closing note), but poisons testability and makes transactional grouping impossible. `SqliteStorage` holds `self._conn` for its lifetime, closes it on `__exit__` / GC. The dashboard gets one connection; the CLI pipeline gets its own (different process, different Streamlit session).
- **`check_same_thread=False`** — required so Streamlit's thread pool can read the same connection across reruns. Writes are still serialized (we have exactly one writer anywhere: the CLI pipeline, or a user clicking a button). Flag this explicitly in the class docstring.
- **Writes wrap `with self._conn:`** per `.claude/rules/storage.md` bullet 2. The current pattern is `conn.commit()` at end of try + `conn.close()` in finally; the new pattern is `with self._conn: self._conn.execute(...)` which commits-or-rolls-back atomically. Read-only methods don't need the context manager.
- **Kill `database.set_db_path(path)` global mutation** — today callers (`cli.py:76`, `web/app.py:16`) call `database.set_db_path(cfg.output.sqlite.path)` before `database.init_db()`. With `Storage` the path is passed at construction; the global `DB_PATH` module variable is deleted.
- **Migrator contract**:
  - Files named `NNNN_<slug>.sql` (four-digit zero-padded int). Migrator reads them sorted by the integer prefix, not lex (so `0010_…` correctly sorts after `0009_…`).
  - Each file is one SQL document. Multi-statement scripts use `executescript`. Migrations must be idempotent under partial-failure because we don't track which *files* ran, only the resulting `user_version` — if a multi-statement script dies halfway, the transaction rolls back and `user_version` stays at the previous value; rerunning starts over.
  - **No down-migrations.** Rollback is `sqlite3 startup_radar.db .dump > backup.sql && rm startup_radar.db && sqlite3 startup_radar.db < backup.sql` applied to the previous tag's checkout. We are not building alembic; `docs/CRITIQUE_APPENDIX.md` §4 is explicit.
  - The migrator logs structured records (`logger.info("migration.applied", version=N, file="...")`) per `.claude/rules/observability.md` bullet 4. Until Phase 13, stdlib `logging` is fine.
- **Retype callers against `Storage`** — every file that imports `database` today (`startup_radar/cli.py`, `web/{app,cache,connections}.py`, `web/pages/{1,2,3,4,5}*.py`, `sources/gmail.py`) gets rewritten to hold a `Storage` reference. Two patterns:
  - **CLI + sources** — explicit injection. `pipeline()` calls `storage = load_storage(cfg)` once and passes it down to the source loop and the sinks. `Source.fetch` already takes `cfg`; we add an optional `storage: Storage | None = None` kwarg for sources that need it (today only `gmail.py:137` does — for `is_processed` / `mark_processed`).
  - **Streamlit (`web/*`)** — `@st.cache_resource` wraps a `get_storage()` factory in `startup_radar/web/cache.py`. Pages call `get_storage()` (cached across reruns, one instance per server process) and then read methods off it. `load_data()` / `overdue_followups()` etc. continue to be `@st.cache_data(ttl=60)` functions that internally call `get_storage()` — the DataFrame is what gets cached, not the connection.
- **Tests** — two new unit files, no integration changes:
  - `tests/unit/test_storage_migrator.py` — fresh DB reaches latest version; mid-version DB (`PRAGMA user_version = 1` manually) applies only pending; double-apply is a no-op; malformed migration raises and leaves `user_version` untouched.
  - `tests/unit/test_storage_sqlite.py` — round-trip smoke: instantiate against `tmp_path / "x.db"`, insert two startups + two job_matches, read them back, verify schema and basic filters. ~60 lines. Replaces the implicit "database.py just works" coverage we've never had.
  - Existing `tests/integration/*` cassette tests need the Gmail path retested because `sources/gmail.py:137`'s `import database` becomes `from startup_radar.storage import …`.
- **Documentation**:
  - `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 12 → ✅ with `phase-10` tag + commit.
  - `docs/PRODUCTION_REFACTOR_PLAN.md` §3.1 target-layout tree — tick mark on `storage/`, drop the `postgres.py` and `migrations/  # alembic` lines (neither is happening; `docs/CRITIQUE_APPENDIX.md` §4 forbids alembic, §12 forbids Postgres).
  - `.claude/CLAUDE.md` repo-layout tree — replace `database.py` row with `startup_radar/storage/{base,sqlite,migrator}.py + migrations/*.sql`; remove the "moves to startup_radar/storage/ Phase 10" annotation; add a Gotcha entry about the single-connection invariant + `check_same_thread=False`.
  - `.claude/rules/storage.md` — already written correctly for this phase (bullet 3 mandates exactly what we're building). One edit: the closing "Note" sentence refers to `database.py:20-23` — update to `startup_radar/storage/sqlite.py:<new line>` after the move.
  - `README.md` "Development" — one-paragraph note on adding a migration (drop a numbered `.sql` in `startup_radar/storage/migrations/`).
- **Harness**:
  - No `.claude/settings.json` change. The `Bash(uv run pytest *)` allowlist already covers the new test files, and no new dep is introduced.
  - Delete the `Edit(database.py)` entry from `.claude/settings.json` permissions **only if present** (grep says it isn't — skip).
  - The `subagents/source-implementer.md` template tells new sources to `import database`. Update to `from startup_radar.storage import Storage` + accept `storage` kwarg.

## Out of scope (deferred)

| Item | Deferred to | Why |
|---|---|---|
| Postgres backend | never | `docs/CRITIQUE_APPENDIX.md` §12 drops it. Single-user, no team. `STARTUP_RADAR_DB_URL` env var is *not* added. |
| SQLAlchemy Core type-safe queries | never | 33 straightforward SQL statements; abstraction tax > benefit per §11 of the appendix. Plain `sqlite3` stays. |
| Alembic | never | §4 of the appendix. Homegrown migrator is ~60 lines vs alembic's multi-file ceremony. |
| Connection pooling | never | Single-writer, single-user. One connection is sufficient; `sqlite3.Connection` is already thread-safe under `check_same_thread=False` for the read-heavy dashboard case. |
| Async `aiosqlite` / `sqlalchemy[asyncio]` | never | §6 of the appendix demotes async entirely; Streamlit is synchronous. |
| `Repository` pattern / per-entity classes (`StartupRepo`, `JobRepo`) | not before ≥3 stores | Premature DRY. The 33 methods split roughly 3:1 between startup-table and everything-else; splitting today would create two half-populated classes. Revisit if the dashboard gains a fourth entity type. |
| `STARTUP_RADAR_DB_URL` env var | Phase 13 (alongside `pydantic-settings` `.env`) | No current caller uses URL-style DB config; `cfg.output.sqlite.path` already covers the one knob we need. |
| Migration test fixtures (pre-Phase-10 DB snapshot) | if a user complains | The migrator's "apply 0001 over a populated DB" path is idempotent by construction (`CREATE TABLE IF NOT EXISTS`), and the failure mode — data loss — would only happen under an *alter*-column migration we don't have. Protects against a scenario that doesn't yet exist. |
| Purge the `_connect()` helper's `PRAGMA journal_mode=WAL` call on every open | already handled in this phase | With one connection per process, WAL is set once at instantiation. No per-call PRAGMA. |
| Delete `startup_radar.db` from the repo / `.gitignore` dance | already handled Phase 7 | DB lives on the `data` branch, not `refactor/v2`. |

## Effort estimate

- **1 engineering day** per `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 12. The code is 90% mechanical — wrap existing function bodies in `self` + replace module-level `DB_PATH` with `self._path`. The migrator itself is ~60 LOC. The caller rewiring (~10 files) is copy-paste once `Storage` is stable.
- Critical path: the Streamlit `@st.cache_resource` Storage singleton. Getting this wrong means either (a) a fresh connection per rerun (worse than today, because we lose WAL setup amortization) or (b) a stale connection that survives across `cfg` reloads. Verified by clicking through pages + reloading `config.yaml` mid-session and confirming the new path takes effect without a server restart.
- Secondary: the `with self._conn:` transactional grouping. Easy to forget on the ~20 write methods. Add a lint-level grep check in `make ci`: `grep -En 'self\._conn\.execute\(".*(INSERT|UPDATE|DELETE)' startup_radar/storage/sqlite.py | grep -v 'with self._conn'` should be empty.
- Tertiary: `sources/gmail.py:137`'s function-scope import (`def …: import database`). Rewrite to module-level `from startup_radar.storage import Storage` and accept storage via the `fetch(cfg, storage=...)` kwarg. Gmail's `is_processed`/`mark_processed` are the only source-level DB calls; other sources stay DB-free.
- Tag at end: `phase-10`.

## Prerequisites

- ✅ Phase 9 (commit `7796c6e`, tag pending `phase-9`). Dashboard is split; pages import `database` at top-level, so the rewire is a one-line `sed` per page.
- ✅ `make ci` green at start. Working tree clean.
- ✅ `sqlite3` stdlib — no new runtime dep.
- ✅ `tests/unit/test_web_smoke.py` exists (Phase 9) — we extend rather than replace.
- No new runtime deps. No new dev deps. No new GH Actions secrets. No new MCP servers.
- ⚠️ Heads-up: the `data` branch holds a live SQLite DB in binary form. After this phase, pulling that DB into a working tree and running the dashboard still works — because `0001_initial.sql` only creates tables IF NOT EXISTS and the existing data remains. Verified by the migrator test `test_migrate_over_populated_db`.

---

## 1. Files to change

| Path | Action | Notes |
|---|---|---|
| `database.py` | **delete** (via `git mv`) | Contents redistributed — schema → `storage/migrations/0001_initial.sql`; functions → `storage/sqlite.py` methods. Keep history via `git mv database.py startup_radar/storage/sqlite.py` then rewrite content. |
| `startup_radar/storage/__init__.py` | **create** | Re-exports: `Storage`, `SqliteStorage`, `load_storage`. ~10 lines. |
| `startup_radar/storage/base.py` | **create** | `Storage` protocol — lists every method the app calls (read methods return pandas DataFrames / dicts / sets; write methods return `int | None`). ~120 lines of `@abstractmethod`-style type hints. |
| `startup_radar/storage/sqlite.py` | **create** (via `git mv` of `database.py`) | `SqliteStorage(Storage)` — the 33 functions become methods. Shared `self._conn`. Init runs migrator. ~700 lines, roughly same as today minus the 33 `_connect()`/`close()` pairs. |
| `startup_radar/storage/migrator.py` | **create** | `apply_pending(conn, migrations_dir, *, logger) -> list[int]`. ~60 lines. |
| `startup_radar/storage/migrations/0001_initial.sql` | **create** | Verbatim extraction of `database.init_db()`'s `executescript` body (ex-lines 29-117). Ends with `PRAGMA user_version = 1;` is NOT included — the migrator sets `user_version` after a successful apply. |
| `startup_radar/cli.py` | edit | Remove `import database` at `cli.py:76`. Replace with `from startup_radar.storage import load_storage`. `pipeline()` becomes `storage = load_storage(cfg); …` and passes `storage` into the source loop + `storage.insert_startups(...)` etc. Drops `database.set_db_path` + `database.init_db` — both are now internal to `load_storage`. |
| `startup_radar/web/app.py` | edit | Drop the `import database` + `database.set_db_path(...)` + `database.init_db()` block at the top (shell lines ~12-20). Replace with `storage = cache.get_storage()` — `get_storage` is the new `@st.cache_resource`-decorated factory in `web/cache.py`. Sidebar's `database.get_connections_last_uploaded()` + `database.get_connections_count()` + `database.import_connections(...)` become `storage.*` calls. |
| `startup_radar/web/cache.py` | edit | Add `get_storage()` (`@st.cache_resource` singleton) and `invalidate_storage()` helper. Rewrite `load_data()` / `overdue_followups()` / `tracker_statuses()` / `connections_count()` to call `get_storage().*` instead of `database.*`. |
| `startup_radar/web/connections.py` | edit | Two `import database` + ~5 `database.foo(...)` calls become `storage: Storage`-typed function parameters. The module already exports helpers, so signatures shift from `def find_tier1(company: str) -> list[...]` to `def find_tier1(storage: Storage, company: str) -> list[...]`. Callers in pages pass their cached `get_storage()`. |
| `startup_radar/web/pages/1_dashboard.py` | edit | `import database` → drop. `database.*` calls already go through `cache.load_data()` — no other changes needed. |
| `startup_radar/web/pages/2_companies.py` | edit | `import database` → drop. Replace ~8 `database.update_startup_*` / `delete_startup` / `insert_activity` calls with `get_storage().*`. Remember the `load_data.clear()` invalidation convention. |
| `startup_radar/web/pages/3_jobs.py` | edit | Same pattern — ~8 write-side calls. |
| `startup_radar/web/pages/4_deepdive.py` | edit | ~7 write-side calls. Also the `_lookup_company`-driven startup insert path. |
| `startup_radar/web/pages/5_tracker.py` | edit | ~14 write-side calls — the heaviest page. |
| `startup_radar/sources/gmail.py` | edit | Remove the function-scope `import database` at `gmail.py:137`. Accept `storage: Storage | None = None` in `fetch(self, cfg, storage=None)`. Call `storage.is_processed(...)` / `storage.mark_processed(...)`. If `storage is None` (back-compat during migration), fall through to a no-op and log a warning — this branch only fires during tests that haven't been updated yet. |
| `startup_radar/sources/base.py` | edit | Update `Source.fetch` signature to `def fetch(self, cfg: AppConfig, storage: Storage | None = None) -> list[Startup]` — optional to keep `rss.py`/`hackernews.py`/`sec_edgar.py` (none of which need storage) untouched. |
| `tests/unit/test_storage_migrator.py` | **create** | ~80 lines. Four tests: fresh-DB, mid-version, idempotent, malformed. |
| `tests/unit/test_storage_sqlite.py` | **create** | ~70 lines. Round-trip + two filter queries + connection lifecycle. |
| `tests/unit/test_web_smoke.py` | edit | One-line fix: the shell now calls `cache.get_storage()` which internally needs a valid `cfg.output.sqlite.path`. Stub via `monkeypatch.setenv("…")` or write a minimal `config.yaml` into `tmp_path`. |
| `tests/integration/test_source_gmail.py` | edit | Pass a `SqliteStorage(tmp_path / "x.db")` into `source.fetch(cfg, storage=storage)`. Cassette unchanged. |
| `Makefile` | edit | Add a `db-migrate` target: `uv run python -c "from startup_radar.storage import load_storage; from startup_radar.config import load_config; load_storage(load_config())"`. One-liner for manual migration runs. |
| `.claude/CLAUDE.md` | edit | Repo-layout tree: replace `database.py` row with `startup_radar/storage/…`. Drop the "moves to startup_radar/storage/ Phase 10" annotation. Add a Gotcha on single-connection + `check_same_thread=False`. Update `.claude/rules/storage.md` cross-reference line. |
| `.claude/rules/storage.md` | edit | One-line tweak: "raw `sqlite3.connect()` per call (today: `database.py:20-23`)" → "per-call connection was retired in Phase 10 in favor of a single process-wide connection in `startup_radar/storage/sqlite.py`". Remove the dangling stdout reference. |
| `.claude/subagents/source-implementer.md` | edit | Template body: `import database` → `from startup_radar.storage import Storage`; `fetch(self, cfg)` → `fetch(self, cfg, storage=None)`. |
| `docs/PRODUCTION_REFACTOR_PLAN.md` | edit | §0a row 12 → ✅ with tag + commit. §3.1 target-layout: tick `storage/`; delete `postgres.py` and `migrations/  # alembic` lines. §3.5 gets a one-line "DONE Phase 10 — homegrown `PRAGMA user_version` migrator; alembic rejected per CRITIQUE_APPENDIX §4" note. |
| `README.md` | edit | "Development" gains a "Schema changes" subsection: drop a `NNNN_<slug>.sql` into `startup_radar/storage/migrations/`, next `startup-radar run` picks it up. |
| `docs/plans/phase-10.md` | **create** | This document. |

### Files explicitly NOT to touch

- `startup_radar/sources/{rss,hackernews,sec_edgar}.py` — none of these touch the DB; they only *return* lists of `Startup` objects. The `storage` kwarg on `Source.fetch` defaults to `None` so their bodies don't change.
- `startup_radar/parsing/*`, `startup_radar/filters.py`, `startup_radar/research/deepdive.py` — all DB-free.
- `startup_radar/config/*` — DB path is already in `AppConfig.output.sqlite.path`; no schema change.
- `sinks/google_sheets.py` — doesn't import `database` (verified via grep).
- `scheduling/*` — shell scripts only.
- `.github/workflows/*.yml` — CI from Phase 8 just runs `make ci`; no workflow edits needed. `daily.yml` invokes `startup-radar run --scheduled` which picks up `load_storage` via `cli.pipeline()` transparently.
- `tests/integration/test_source_{rss,hackernews,sec_edgar}.py` — these sources don't take `storage`. Unchanged.
- `config.yaml`, `config.example.yaml` — no shape changes.

---

## 2. New/changed file shapes

### 2.1 `startup_radar/storage/base.py` — protocol

```python
"""Storage protocol. All DB access in the app goes through this interface.

Exists primarily to make ``tests/unit/`` fakeable without disk I/O. Only one
real implementation today (``SqliteStorage``); if we ever add a second, the
protocol keeps the swap honest.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

import pandas as pd

from startup_radar.models import JobMatch, Startup


class Storage(Protocol):
    # --- schema ---
    def migrate_to_latest(self) -> list[int]: ...
    def user_version(self) -> int: ...
    def close(self) -> None: ...

    # --- reads: startups / jobs ---
    def get_all_startups(self) -> pd.DataFrame: ...
    def get_all_job_matches(self) -> pd.DataFrame: ...
    def get_existing_companies(self) -> set[str]: ...
    def get_rejected_companies(self) -> set[str]: ...
    def get_existing_job_keys(self) -> set[str]: ...

    # --- writes: startups / jobs ---
    def insert_startups(self, startups: list[Startup | dict]) -> int: ...
    def insert_job_matches(self, jobs: list[JobMatch | dict]) -> int: ...
    def update_startup_website(self, company_name: str, website: str) -> None: ...
    def update_startup_status(self, company_name: str, status: str) -> None: ...
    def update_job_status(self, company_name: str, role_title: str, status: str) -> None: ...
    def update_job_notes(self, company_name: str, role_title: str, notes: str) -> None: ...
    def delete_startup(self, company_name: str) -> None: ...
    def delete_job_match(self, company_name: str, role_title: str) -> None: ...

    # --- processed-items dedup (sources) ---
    def is_processed(self, source: str, item_id: str) -> bool: ...
    def mark_processed(self, source: str, item_ids: Iterable[str]) -> None: ...

    # --- activities / tracker ---
    def insert_activity(self, activity: dict) -> int: ...
    def get_activities(self, company_name: str | None = None) -> pd.DataFrame: ...
    def get_overdue_followups(self, today: str) -> pd.DataFrame: ...
    def get_tracker_status(self, company_name: str) -> dict: ...
    def upsert_tracker_status(
        self, company_name: str, status: str, role: str = "", notes: str = ""
    ) -> None: ...
    def get_all_tracker_statuses(self) -> dict: ...
    def delete_tracker_entry(self, company_name: str) -> None: ...
    def get_tracker_summary(self) -> pd.DataFrame: ...

    # --- connections (LinkedIn CSV) ---
    def import_connections(self, rows: list[dict]) -> int: ...
    def get_connections_count(self) -> int: ...
    def get_connections_last_uploaded(self) -> str: ...
    def search_connections_by_company(self, company_name: str) -> pd.DataFrame: ...
    def search_connections_by_companies(self, company_names: list[str]) -> pd.DataFrame: ...
    def hide_intro(self, connection_url: str, company_name: str) -> None: ...
    def get_hidden_intros(self, company_name: str) -> set[str]: ...
```

### 2.2 `startup_radar/storage/sqlite.py` — head

```python
"""SqliteStorage — single-connection SQLite backend for Startup Radar.

One ``sqlite3.Connection`` per process. WAL. ``check_same_thread=False``
so Streamlit's thread pool can share reads across reruns.

*All writes* wrap ``with self._conn:`` for atomic commit-or-rollback
(`.claude/rules/storage.md` bullet 2). Read methods do not — they are not
transactional by design.

Schema versioning: ``PRAGMA user_version`` drives the homegrown migrator
in ``startup_radar/storage/migrator.py``. Alembic explicitly rejected per
``docs/CRITIQUE_APPENDIX.md`` §4.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import pandas as pd

from startup_radar.models import JobMatch, Startup
from startup_radar.storage.migrator import apply_pending

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

log = logging.getLogger(__name__)


class SqliteStorage:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn = sqlite3.connect(
            str(path), check_same_thread=False, isolation_level=None
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # leave in autocommit; explicit ``with self._conn:`` wraps each write.

    # --- schema ------------------------------------------------------------

    def migrate_to_latest(self) -> list[int]:
        applied = apply_pending(self._conn, _MIGRATIONS_DIR, logger=log)
        if applied:
            log.info("storage.migrated", extra={"versions": applied, "path": str(self._path)})
        return applied

    def user_version(self) -> int:
        (v,) = self._conn.execute("PRAGMA user_version").fetchone()
        return int(v)

    def close(self) -> None:
        self._conn.close()

    # --- reads: startups / jobs -------------------------------------------

    def get_all_startups(self) -> pd.DataFrame:
        df = pd.read_sql_query(
            """SELECT company_name, website, description, funding_stage, amount_raised,
                      location, source, date_found, status
               FROM startups ORDER BY date_found DESC, id DESC""",
            self._conn,
        )
        df.columns = [
            "Company Name", "Website", "Description", "Funding Stage",
            "Amount Raised", "Location", "Source", "Date Found", "Status",
        ]
        df["Website"] = df["Website"].fillna("")
        df["Website"] = df["Website"].apply(
            lambda x: f"https://{x}" if x and not x.startswith("http") else x
        )
        df["Status"] = df["Status"].fillna("")
        return df

    # ... (remaining ~700 lines — method bodies are verbatim ports of the
    # ... former module-level functions, with ``conn = _connect()`` removed
    # ... and ``conn.close()`` deleted. Writes gain ``with self._conn:``.)
```

Audit: every former `conn = _connect()` / `try: … finally: conn.close()` pair collapses to a single `self._conn` reference. Estimated delta: -66 LOC (33 functions × 2 lines each).

### 2.3 `startup_radar/storage/migrator.py`

```python
"""PRAGMA user_version migrator.

Walks ``NNNN_*.sql`` files in ``migrations/``, applies any above the
database's current ``user_version`` inside one transaction each, bumps the
pragma after success. No down-migrations (``docs/CRITIQUE_APPENDIX.md`` §4).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

_FILE_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def _discover(migrations_dir: Path) -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for p in sorted(migrations_dir.glob("*.sql")):
        m = _FILE_RE.match(p.name)
        if not m:
            raise ValueError(f"bad migration filename: {p.name}")
        out.append((int(m.group(1)), p))
    if [v for v, _ in out] != sorted(v for v, _ in out):
        raise ValueError("migrations are not strictly ascending")
    for i, (v, _) in enumerate(out, start=1):
        if v != i:
            raise ValueError(f"expected migration {i:04d}, found {v:04d}")
    return out


def apply_pending(
    conn: sqlite3.Connection,
    migrations_dir: Path,
    *,
    logger: logging.Logger | None = None,
) -> list[int]:
    log = logger or logging.getLogger(__name__)
    (current,) = conn.execute("PRAGMA user_version").fetchone()
    applied: list[int] = []
    for version, path in _discover(migrations_dir):
        if version <= current:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            with conn:  # atomic: commits on success, rolls back on exception
                conn.executescript(sql)
                conn.execute(f"PRAGMA user_version = {version}")
        except sqlite3.Error:
            log.exception("migration.failed", extra={"version": version, "file": path.name})
            raise
        log.info("migration.applied", extra={"version": version, "file": path.name})
        applied.append(version)
    return applied
```

Notes:
- Filename validation catches typos (`001_foo.sql`, `0001_Foo.sql`, gaps) at import time rather than mid-migration.
- Each migration is its own `with conn:` block — `PRAGMA user_version = N` is inside the transaction, so a mid-script failure rolls *both* the schema edit and the pragma back. Idempotence guaranteed.
- The stdlib `logging` calls here will be replaced by `structlog.get_logger(__name__)` in Phase 13 — `extra={...}` is already structured, so it's a drop-in.

### 2.4 `startup_radar/storage/migrations/0001_initial.sql`

Verbatim lift of the `executescript` body from `database.py:29-117`. No `BEGIN`/`COMMIT` — the migrator wraps the whole thing in `with conn:`. Ends with the last `CREATE TABLE`; no trailing `PRAGMA user_version` (the migrator sets it).

```sql
-- 0001_initial.sql — baseline schema.
-- All tables use CREATE TABLE IF NOT EXISTS so this migration is safe to
-- re-apply over an already-populated pre-Phase-10 DB (user_version=0).

CREATE TABLE IF NOT EXISTS startups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    description TEXT DEFAULT '',
    funding_stage TEXT DEFAULT '',
    amount_raised TEXT DEFAULT '',
    location TEXT DEFAULT '',
    website TEXT DEFAULT '',
    source TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    date_found TEXT,
    status TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_startups_name
    ON startups(company_name COLLATE NOCASE);

-- job_matches, connections, connections_meta, hidden_intros, processed_items,
-- activities, tracker_status — all copied verbatim from database.py:48-117.
```

### 2.5 `startup_radar/storage/__init__.py`

```python
"""Storage subpackage — single entry point for DB access."""

from __future__ import annotations

from pathlib import Path

from startup_radar.config import AppConfig
from startup_radar.storage.base import Storage
from startup_radar.storage.sqlite import SqliteStorage


def load_storage(cfg: AppConfig) -> Storage:
    """Instantiate the configured backend, run pending migrations, return."""
    if not cfg.output.sqlite.enabled:
        raise RuntimeError("sqlite output is disabled; no other backend configured")
    storage = SqliteStorage(Path(cfg.output.sqlite.path))
    storage.migrate_to_latest()
    return storage


__all__ = ["Storage", "SqliteStorage", "load_storage"]
```

One entry point. Callers never instantiate `SqliteStorage` directly outside tests.

### 2.6 `startup_radar/web/cache.py` diff

```diff
 import streamlit as st

-import database
+from startup_radar.config import load_config
+from startup_radar.storage import Storage, load_storage


+@st.cache_resource
+def get_storage() -> Storage:
+    return load_storage(load_config())
+
+
 @st.cache_data(ttl=60)
 def load_data() -> tuple:
-    return database.get_all_startups(), database.get_all_job_matches()
+    s = get_storage()
+    return s.get_all_startups(), s.get_all_job_matches()


 @st.cache_data(ttl=60)
 def overdue_followups(today_iso: str):
-    return database.get_overdue_followups(today_iso)
+    return get_storage().get_overdue_followups(today_iso)


 @st.cache_data(ttl=60)
 def tracker_statuses() -> dict:
-    return database.get_all_tracker_statuses()
+    return get_storage().get_all_tracker_statuses()


 @st.cache_data(ttl=60)
 def connections_count() -> int:
-    return database.get_connections_count()
+    return get_storage().get_connections_count()
```

The `@st.cache_resource`-wrapped `get_storage` gives us a single process-wide `SqliteStorage` instance; Streamlit's reruns share it without re-running the migrator. `load_data.clear()` after inserts stays unchanged.

### 2.7 `startup_radar/cli.py` diff (pipeline body)

```diff
 def pipeline() -> int:
     cfg = load_config()
-    import database
-    if cfg.output.sqlite.enabled:
-        database.set_db_path(cfg.output.sqlite.path)
-    database.init_db()
+    from startup_radar.storage import load_storage
+    storage = load_storage(cfg)

     stats: dict[str, int] = {}
     for name, source in SOURCES.items():
         if not _enabled(cfg, source.enabled_key):
             continue
         try:
-            startups = source.fetch(cfg)
+            startups = source.fetch(cfg, storage=storage)
         except Exception:
             log.exception("source.failed", extra={"source": name})
             continue
-        kept = database.insert_startups(startups)
+        kept = storage.insert_startups(startups)
         stats[name] = kept
     …
+    storage.close()
     return 0 if any(stats.values()) else 1
```

### 2.8 `tests/unit/test_storage_migrator.py` (skeleton)

```python
"""Migrator unit tests. Avoid real filesystem SQL by writing .sql files into
``tmp_path / "migrations"`` and pointing the migrator at them directly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from startup_radar.storage.migrator import apply_pending


def _write(dir_: Path, name: str, body: str) -> None:
    (dir_ / name).write_text(body, encoding="utf-8")


def test_fresh_db_applies_all(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "0001_init.sql", "CREATE TABLE t (x INTEGER);")
    _write(migrations, "0002_add.sql", "ALTER TABLE t ADD COLUMN y INTEGER;")
    conn = sqlite3.connect(":memory:")

    applied = apply_pending(conn, migrations)

    assert applied == [1, 2]
    (v,) = conn.execute("PRAGMA user_version").fetchone()
    assert v == 2


def test_mid_version_applies_only_pending(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "0001_init.sql", "CREATE TABLE t (x INTEGER);")
    _write(migrations, "0002_add.sql", "ALTER TABLE t ADD COLUMN y INTEGER;")
    conn = sqlite3.connect(":memory:")
    conn.executescript("CREATE TABLE t (x INTEGER); PRAGMA user_version = 1;")

    applied = apply_pending(conn, migrations)

    assert applied == [2]


def test_idempotent(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "0001_init.sql", "CREATE TABLE t (x INTEGER);")
    conn = sqlite3.connect(":memory:")

    apply_pending(conn, migrations)
    assert apply_pending(conn, migrations) == []


def test_malformed_rolls_back(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "0001_good.sql", "CREATE TABLE a (x INTEGER);")
    _write(migrations, "0002_bad.sql", "CREATE TABLE a (x INTEGER); GARBAGE;")
    conn = sqlite3.connect(":memory:")

    with pytest.raises(sqlite3.Error):
        apply_pending(conn, migrations)

    (v,) = conn.execute("PRAGMA user_version").fetchone()
    assert v == 1  # 0001 succeeded, 0002 rolled back cleanly


def test_filename_validation(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "001_short.sql", "CREATE TABLE t (x INTEGER);")
    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="bad migration filename"):
        apply_pending(conn, migrations)


def test_gap_rejected(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    _write(migrations, "0003_c.sql", "CREATE TABLE c (x INTEGER);")
    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="expected migration 0002"):
        apply_pending(conn, migrations)
```

Six tests, all hermetic (`:memory:` SQLite, no fixtures). Runs in <1s.

### 2.9 `tests/unit/test_storage_sqlite.py` (skeleton)

```python
"""Smoke test for SqliteStorage. Round-trips two startups + one job_match
through the real schema on tmp-path storage. Intentionally minimal —
per-method coverage lives in the integration tests once they're pointed at
the new class.
"""

from __future__ import annotations

from pathlib import Path

from startup_radar.models import JobMatch, Startup
from startup_radar.storage.sqlite import SqliteStorage


def test_round_trip(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "x.db")
    storage.migrate_to_latest()

    inserted = storage.insert_startups(
        [
            Startup(company_name="Acme", source="rss"),
            Startup(company_name="Globex", source="hackernews"),
        ]
    )
    assert inserted == 2

    df = storage.get_all_startups()
    assert set(df["Company Name"]) == {"Acme", "Globex"}

    storage.insert_job_matches(
        [JobMatch(company_name="Acme", role_title="Staff Engineer", source="rss")]
    )
    jobs = storage.get_all_job_matches()
    assert len(jobs) == 1
    assert jobs.iloc[0]["Role"] == "Staff Engineer"

    storage.close()


def test_user_version_after_migrate(tmp_path: Path) -> None:
    s = SqliteStorage(tmp_path / "x.db")
    s.migrate_to_latest()
    assert s.user_version() == 1
    # double-migrate is a no-op
    assert s.migrate_to_latest() == []
    s.close()
```

---

## 3. Execution order

1. **Branch**: stay on `refactor/v2`. Working tree clean.
2. **Skeleton** — create `startup_radar/storage/{__init__,base,sqlite,migrator}.py` as stubs + empty `migrations/` dir. Commit separately so the `git mv` in step 3 has a target.
3. **`git mv database.py startup_radar/storage/sqlite.py`** — preserves history. File still has free functions at this point; will be refactored in step 4.
4. **Refactor `sqlite.py` into a class** — wrap every function as a method of `SqliteStorage`, strip `_connect()`/`close()` boilerplate, replace module-level `DB_PATH` with `self._path`, add `with self._conn:` to all writes. Commit #1 of the phase.
5. **Extract schema** — copy the `executescript` body from `init_db()` (now `_legacy_init_db`) into `startup_radar/storage/migrations/0001_initial.sql`. Replace `_legacy_init_db` with a call to `apply_pending`. Delete the legacy function. Commit #2.
6. **Write the migrator** — `migrator.py` per §2.3. Run `make test` — the migrator unit tests should pass in isolation before we touch callers. Commit #3.
7. **Introduce `load_storage`** — wire `__init__.py` per §2.5. Commit #4.
8. **Rewire the CLI** — `cli.py` per §2.7 — smallest caller, one file, verify with `uv run startup-radar run --dry-run`-equivalent (actually run the pipeline against a tmp config).
9. **Rewire the dashboard** — `web/cache.py` (§2.6), `web/app.py` (drop `database.*` calls), `web/connections.py` (signature shift), then the five pages. Commit per file group so `AppTest` can confirm each step.
10. **Rewire Gmail source** — `sources/base.py` signature + `sources/gmail.py:137` function-scope import → module-level. Verify via `tests/integration/test_source_gmail.py`.
11. **Write storage tests** — `test_storage_migrator.py` + `test_storage_sqlite.py`. Run `make test-unit`.
12. **Fix the web smoke test** — `tests/unit/test_web_smoke.py` needs a valid `config.yaml` so `load_storage` can resolve a path. Stub with `monkeypatch.chdir(tmp_path)` + minimal yaml.
13. **Manual QA** — `uv run startup-radar run` against a clean tmp DB (verify migrator applies 0001 and inserts work); `uv run startup-radar serve` (verify dashboard reads work and the pipeline-trigger button still writes); pull the prod DB from the `data` branch and run both against it (verify the pre-Phase-10 DB is silently upgraded).
14. **`make ci`** — must be green. Pay attention to mypy on the new `Storage` protocol and pandas return types.
15. **Docs pass** — `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 12 + §3.1 + §3.5; `.claude/CLAUDE.md` layout tree + gotchas; `.claude/rules/storage.md` line-number fix; `README.md` schema-changes subsection.
16. **Tag** — `git tag phase-10 && git push origin phase-10`. User-driven per CLAUDE.md's "do not delegate commits" rule.

---

## 4. Rollback plan

Multi-commit phase. Revert strategy by severity:

- **Caught in CI before push**: `git reset --soft <phase-10-parent>` + re-work.
- **Caught after local merge, pre-tag**: `git revert <merge-commit>` (mostly a single merge commit thanks to the squash policy).
- **Caught after push + tag**: `git revert` the range, `git tag -d phase-10`, `git push --delete origin phase-10`. No DB migration needed — `0001_initial.sql` is a no-op over an already-populated schema, so reverted code reading the same DB file just works.
- **Data-corruption escape hatch**: the migrator never destroys data (no `DROP`, no `ALTER … DROP COLUMN`). Worst case, a corrupt schema bump leaves `user_version` wrong — fix by `sqlite3 startup_radar.db "PRAGMA user_version = N"` manually.

Because `database.py` moves via `git mv`, revert restores it at the repo root. All callers flip back to `import database` via the same revert.

---

## 5. Exit criteria

- [ ] `database.py` at repo root no longer exists; `startup_radar/storage/sqlite.py` exists with `class SqliteStorage`.
- [ ] `startup_radar/storage/{__init__,base,migrator}.py` all exist.
- [ ] `startup_radar/storage/migrations/0001_initial.sql` exists and is byte-identical to the old `init_db()` `executescript` body (verified via side-by-side diff).
- [ ] No `import database` anywhere in the codebase. `grep -rn "import database" startup_radar/ tests/` returns nothing.
- [ ] No `database.set_db_path` or `database.init_db` anywhere. Same grep.
- [ ] `SqliteStorage.__init__` sets WAL + `check_same_thread=False`.
- [ ] Every write method uses `with self._conn:`. Verified by the lint-grep in §Effort estimate.
- [ ] `PRAGMA user_version` equals the highest migration number after `migrate_to_latest()`.
- [ ] `make ci` green. Both new test files pass. `tests/unit/test_web_smoke.py` still passes. `tests/integration/test_source_gmail.py` still passes.
- [ ] `uv run startup-radar run` writes to the configured DB path and bumps `user_version` to 1 on a fresh DB.
- [ ] `uv run startup-radar serve` opens the dashboard; all five pages render; "Run pipeline now" writes and invalidates the cache.
- [ ] The `data`-branch DB still works: pull it, point config at it, run the dashboard — no schema errors.
- [ ] `.claude/CLAUDE.md` repo-layout tree updated; `.claude/rules/storage.md` line-number reference corrected.
- [ ] `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 12 → ✅ with `phase-10` tag + commit SHA. §3.1 postgres/alembic lines deleted.
- [ ] Tag `phase-10` pushed (by the user).

---

## 6. Post-phase note

**Phase 11 (§0a row 13): structlog + retries + per-source failure counters.** With `Storage` in place, Phase 11 can cleanly add a `runs` table (`CREATE TABLE runs (id INTEGER PK, source TEXT, started_at TEXT, ended_at TEXT, items_fetched INTEGER, items_kept INTEGER, error TEXT)`) via a second migration (`0002_runs_table.sql`) — the migrator machinery is ready. structlog replaces the stdlib `logging` calls in `migrator.py` + `sqlite.py` as a one-liner (`structlog.get_logger(__name__)`); the `extra={...}` payloads already match structlog's kwarg-based API.

**Also unlocked**: per-page `AppTest` smoke tests (deferred from Phase 9) can now stub `cache.get_storage` with a `SqliteStorage(":memory:")` fixture instead of hitting disk. One `conftest.py` fixture covers all five pages.
