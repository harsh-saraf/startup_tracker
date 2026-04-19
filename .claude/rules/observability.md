---
paths:
  - "**/*.py"
---

# Observability rules

- **Must:** use `structlog.get_logger(__name__)` for new modules (Phase 13 dependency). Until then, the existing `logging` setup in `daily_run.py` is acceptable.
- **Never:** use `print()` in library code (`sources/`, `sinks/`, `database.py`, `filters.py`, `connections.py`). `print()` is allowed in `main.py`, `daily_run.py`, `deepdive.py` until the Typer CLI lands (Phase 6).
- **Never:** bare `except:` or `except Exception:` without re-raising or logging at `error` level with traceback.
- **Must:** log fields are structured: `logger.info("source.fetched", source="rss", count=12)` — not formatted strings.
- **Must:** per-source success/failure increments a counter (Phase 13: persisted to `runs` table; until then, just log).
- **Never:** log secrets, OAuth tokens, full email bodies, or full `Authorization` headers.
- **Must:** HTTP errors include the URL and status code in the log record.
- **Must:** when catching to return `[]` (e.g., a dead RSS feed), log at `warning` with the source name and the exception message.
