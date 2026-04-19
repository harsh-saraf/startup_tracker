---
paths:
  - "database.py"
  - "startup_radar/storage/**"
---

# Storage rules

- **Must:** all SQL goes through `database.py` functions. No inline `sqlite3` in callers.
- **Must:** every write is wrapped in a single `with conn:` block (transactional).
- **Must:** schema changes bump `PRAGMA user_version` and ship a numbered `.sql` under `migrations/` (homegrown migrator — **NOT** alembic; see `docs/CRITIQUE_APPENDIX.md` §4).
- **Never:** open a new connection inside a hot loop. Accept `conn` as parameter or use a module-level pooled connection.
- **Never:** edit `*.db` files directly. Use SQL.
- **Must:** any new column has a `DEFAULT` so old rows don't break.
- **Must:** indexes on any column used in `WHERE` of a query called from the dashboard.
- **Never:** store secrets in the DB. Use `.env` / `~/.config/startup-radar/`.
- **Note:** raw `sqlite3.connect()` per call (today: `database.py:20-23`) is **not** a perf bug for single-user SQLite. Refactor reason is testability + transactional grouping.
