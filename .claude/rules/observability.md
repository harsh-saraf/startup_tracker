---
paths:
  - "**/*.py"
---

# Observability rules

- **Must:** use `from startup_radar.observability.logging import get_logger; log = get_logger(__name__)` in every new module. Pass structured kwargs, not `extra={...}`.
- **Must:** pipeline entry points (`cli.py` `@app.callback`, `web/app.py` shell) call `configure_logging(json=...)` exactly once. No other module touches root-logger handlers or calls `logging.basicConfig`.
- **Never:** use `print()` in library code (`startup_radar/sources/`, `sinks/`, `startup_radar/storage/`, `startup_radar/filters.py`, `startup_radar/web/**`). `print()` is allowed in `startup_radar/cli.py`, `startup_radar/research/deepdive.py`, and `tests/`.
- **Never:** bare `except:` or `except Exception:` without re-raising or logging at `error` level with traceback.
- **Must:** raise `StartupRadarError` subclasses (from `startup_radar/errors.py` — today: `ConfigError`, `SourceError`) for known, user-facing failure modes the CLI should surface as a single-line error. Generic `Exception` is reserved for bugs — the `@_catch_errors` boundary in `cli.py` lets them propagate with full tracebacks, and `--debug` threads `exc_info=True` into the `cli.error` log for known failures too.
- **Must:** log fields are structured: `log.info("source.fetched", source="rss", count=12)` — not formatted strings, never `extra={}`.
- **Must:** per-source success/failure is persisted via `storage.record_run(...)` in the pipeline loop. `storage.failure_streak(source_key)` drives the `status` + `doctor` streak warning (>2 = ⚠).
- **Never:** log secrets, OAuth tokens, full email bodies, or full `Authorization` headers.
- **Must:** HTTP errors include the URL and status code in the log record.
- **Must:** when catching to return `[]` (e.g., a dead RSS feed), log at `warning` with the source name and the exception message.
- **Must:** network calls in sources go through `startup_radar.sources._retry.retry(fn, on=(...), context={...})` — three attempts, `(1, 2, 4)` s backoff. Don't hand-roll retry loops; don't pull in `tenacity` / `backoff`.
