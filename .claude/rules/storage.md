---
paths:
  - "startup_radar/storage/**"
---

# Storage rules

- **Must:** all SQL goes through `SqliteStorage` methods in `startup_radar/storage/sqlite.py`. No inline `sqlite3` in callers.
- **Must:** callers obtain storage via `load_storage(cfg)` (CLI/tests) or `get_storage()` (dashboard, `@st.cache_resource` singleton). Never instantiate `SqliteStorage` directly outside tests.
- **Must:** every write is wrapped in a single `with self._conn:` block (transactional commit-or-rollback). Read methods do not.
- **Must:** schema changes bump `PRAGMA user_version` and ship a numbered `NNNN_<slug>.sql` under `startup_radar/storage/migrations/` (homegrown migrator — **NOT** alembic; see `docs/CRITIQUE_APPENDIX.md` §4). The migrator rejects gaps and bad filenames at load time.
- **Must:** every migration uses `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` so it's idempotent over pre-Phase-10 populated DBs.
- **Never:** down-migrations. Rollback = restore from the `startup-radar backup` tarball or pull from the `data` branch.
- **Never:** call `sqlite3.connect()` directly. `SqliteStorage` holds one connection for its lifetime (WAL, `check_same_thread=False`).
- **Never:** edit `*.db` files directly. Use SQL.
- **Must:** any new column has a `DEFAULT` so old rows don't break.
- **Must:** indexes on any column used in `WHERE` of a query called from the dashboard.
- **Never:** store secrets in the DB. Use `.env` / `~/.config/startup-radar/`.
- **Note:** per-call `sqlite3.connect()` was retired in Phase 10 in favor of the single process-wide connection in `startup_radar/storage/sqlite.py`. The single-connection invariant exists for testability + transactional grouping, not perf — SQLite open cost was never the bottleneck.
