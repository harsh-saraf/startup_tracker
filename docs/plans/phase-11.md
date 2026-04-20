# Phase 11 Execution Plan — structlog + retries + per-source failure counters

> Close row 13 in `docs/PRODUCTION_REFACTOR_PLAN.md` §0a. Migrate the ad-hoc stdlib `logging.getLogger(__name__)` call-sites under `startup_radar/` to a single structlog pipeline; wrap the four sources' network calls in a ~40-line retry helper (no `tenacity` per `docs/CRITIQUE_APPENDIX.md` §7); add a `runs` table via migration `0002_runs_table.sql` and surface per-source failure streaks in `startup-radar status` + `doctor`. **Explicitly NOT** Sentry (Phase 13), **NOT** a circuit breaker (per §0a Demotes — "per-source failure flag is enough"), **NOT** `tenacity` / `backoff`.

## Phase summary

- **structlog as the one logging pipeline.** New `startup_radar/observability/logging.py` exposes `configure_logging(json: bool) -> None`. Called once at CLI startup (`cli.app` callback) and once at dashboard startup (`web/app.py` shell). Pretty `ConsoleRenderer` locally; `JSONRenderer` when `CI=1` or `STARTUP_RADAR_LOG_JSON=1`. Library logs (google-api-python-client, urllib3, feedparser) flow in via `structlog.stdlib.LoggerFactory` so we keep a single output stream even for deps we don't own.
- **Processor chain, explicit and boring:** `merge_contextvars → add_log_level → TimeStamper(fmt="iso", utc=True) → StackInfoRenderer → format_exc_info → (JSONRenderer | ConsoleRenderer)`. `merge_contextvars` lets the pipeline loop bind `source=<name>` once per iteration via `structlog.contextvars.bound_contextvars("source", name)` instead of every call-site repeating the field.
- **Collapse `extra={...}` into kwargs.** Every existing `log.info("event", extra={"source": x})` becomes `log.info("event", source=x)` — structlog's kwarg-native API matches what `.claude/rules/observability.md` already mandates. This is mechanical and grepable; the audit below enumerates each site.
- **`print()` policy unchanged.** `.claude/CLAUDE.md` rule stands — `print()` is allowed only in `startup_radar/cli.py`, `startup_radar/research/deepdive.py`, and `tests/`, because stdout in those tiers is the UX. structlog replaces `logging.getLogger` in library code, not the user-facing CLI prints. The `_LogStream` print-redirector in `cli.py` (lines 52-69) stays — it's still how scheduled mode captures pipeline output into `logs/YYYY-MM-DD.log`; Phase 13 may rewire it against structlog's stdlib bridge but Phase 11 doesn't.
- **Retry helper, not a library.** New `startup_radar/sources/_retry.py` — ~40 LOC. Exposes either `@with_retry(attempts=3, backoff=(1, 2, 4))` or a plain `retry(fn, *, attempts, backoff, on=(requests.RequestException, TimeoutError))` callable. No `tenacity` (`docs/CRITIQUE_APPENDIX.md` §7 — "No retry libraries — stdlib or simple helper"). No `backoff` library. Helper uses `time.sleep`; tests monkeypatch it. Retries only the *network* call — never the parser — so a malformed feed that makes `feedparser.parse` raise does NOT waste three round-trips.
- **One retry surface per source.** Target lines:
  - `sources/rss.py:106` — `feedparser.parse(feed_url)` wrapped (parser *and* fetcher are the same call; acceptable).
  - `sources/hackernews.py:61-70` — the `requests.get(ALGOLIA_URL, …)` call.
  - `sources/sec_edgar.py:79` — `requests.get(EDGAR_SEARCH_URL, …)`.
  - `sources/gmail.py:155` (`labels().list`), `:173-178` (`messages().list`), `:194` (per-message `.get`) — idempotent GETs, safe to retry. The OAuth flow itself (`_get_service`, line 46) is NOT wrapped — auth failures should surface immediately, not stall for three backoff cycles.
- **No retries on `Source` ABC.** The ABC stays thin per its current docstring ("subclasses MUST set `name` + `enabled_key`; `fetch(cfg, storage=None)` is the only required method"). Retries are a per-call-site decorator, not a base-class behavior — keeps sources that don't need retries (none today, but an eventual scraper that *writes* shouldn't retry blindly) free to opt out.
- **`cfg.network.timeout_seconds`.** New leaf under `AppConfig.network` (new sub-model) with default `10`. Sources that already pass `timeout=` stay as-is but grow a `cfg.network.timeout_seconds` override path — the retry helper reads the cfg timeout when wrapping the call. Chosen over `AppConfig.sources.<each>.timeout` because timeouts are a *transport* concern shared by all sources; the per-source knob exists today (`timeout=20` in EDGAR, `timeout=15` in HN) only because we never had a central one.
- **`runs` table + migration 0002.** `startup_radar/storage/migrations/0002_runs_table.sql` creates:
  ```sql
  CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source TEXT NOT NULL,
      started_at TEXT NOT NULL,
      ended_at TEXT,
      items_fetched INTEGER,
      items_kept INTEGER,
      error TEXT,
      user_version_at_run INTEGER
  );
  CREATE INDEX IF NOT EXISTS idx_runs_source_id ON runs(source, id DESC);
  ```
  Idempotent (`IF NOT EXISTS`) just like 0001; strict filename ascending validated by the migrator. The index exists for `failure_streak` — which scans `WHERE source = ?` newest-first.
- **`Storage` gains three methods.** `record_run(source, started_at, ended_at, items_fetched, items_kept, error) -> int`, `last_run(source) -> dict | None`, `failure_streak(source) -> int`. Added to both `storage/base.py` Protocol and `storage/sqlite.py`. The `runs` insert wraps `with self._conn:` per `.claude/rules/storage.md` bullet 2.
- **`cli.pipeline()` wraps each source call.** Around the existing `source.fetch(cfg, storage=storage)` loop: `started_at = datetime.utcnow().isoformat()`; try; on exception, capture `err = repr(e)`; finally, `storage.record_run(name, started_at, ended_at=datetime.utcnow().isoformat(), items_fetched=len(found), items_kept=…, error=err)`. One row per source per invocation.
- **`cli status` extension.** Today's output ends with `DB rows:`; add a new block `Per-source health:` iterating `cfg.sources.*.enabled`, showing `last-run age | streak`. Pure read; no new columns.
- **`cli doctor` extension.** After the existing per-source healthcheck loop, cross-check `storage.failure_streak(name) > 2` and emit a `⚠ source.<name> failing N consecutive runs` warning (warning, NOT a failure — `doctor` exit-code stays 0 for transient network per single-user scope).
- **Dashboard: deferred.** A "Pipeline health" strip on page 1 is tempting but out of scope — bundling UX polish with plumbing dilutes both. Listed in "Out of scope" pointing at Phase 14.
- **Tests.** Six new files:
  - `tests/unit/test_retry.py` — happy path, retries-then-succeeds, retries-then-fails, honours backoff, only retries on configured exception types.
  - `tests/unit/test_observability_logging.py` — `configure_logging(json=True)` emits a valid JSON object per call with `event`, `level`, `timestamp`; `configure_logging(json=False)` renders ANSI-stripped pretty output; `merge_contextvars` carries `source=` into nested log lines.
  - `tests/unit/test_storage_runs.py` — `record_run` + `last_run` round-trip; `failure_streak` = 0 after success, N after N failures, resets after success.
  - `tests/unit/test_storage_migrator.py` — extend existing file with one test: start at `user_version=1`, apply 0002, verify `user_version=2` and existing `startups` rows preserved.
  - `tests/integration/test_source_*.py` — extend each of the four existing files with a "fails twice, then succeeds" test using `monkeypatch` on `time.sleep` (cheap) and either a vcrpy `--record-mode=new_episodes` recording or a simple `responses`-style mock that raises twice then returns a cassette body. Prefer the monkeypatch route — the retry helper is tested in isolation already; what we want here is confirming the wiring, not re-testing the helper.
  - `tests/unit/test_cli_status.py` + `tests/unit/test_cli_doctor.py` — extend to assert the new `Per-source health:` block + failure-streak warning.
- **Harness updates.**
  - `.claude/rules/observability.md` — add one bullet: "Call `startup_radar.observability.logging.configure_logging(json=...)` once per process at startup; never re-configure."
  - `.claude/CLAUDE.md` — add a Gotcha: "Set `STARTUP_RADAR_LOG_JSON=1` for JSON logs locally; CI sets `CI=1` which auto-selects JSON. Do NOT call `logging.basicConfig`; it short-circuits structlog's stdlib bridge." Also one line in the repo-layout tree for `observability/logging.py`.
  - No new subagent.

## Out of scope (deferred)

| Item | Deferred to | Why |
|---|---|---|
| Sentry SDK / error aggregation | Phase 13 | §4.3 of the refactor plan explicitly schedules Sentry for Phase 13 alongside `pydantic-settings` `.env` (the natural home of `SENTRY_DSN`). Phase 11 leaves the structlog pipeline Sentry-ready (adding `sentry_sdk.integrations.logging.EventHandler` in Phase 13 is a one-processor addition) without shipping it today. |
| `tenacity` / `backoff` / any retry library | never | `docs/CRITIQUE_APPENDIX.md` §7 rules out retry libraries. A 40-LOC helper covers 100% of our needs: three attempts, exponential backoff, fixed exception list. Tenacity's generality (`retry_if_exception_type`, `wait_combine`, stop conditions) is tax we don't pay. |
| Per-source custom backoff curves | never | `(1, 2, 4)` is fine for every source. SEC EDGAR's 10 req/s ceiling is enforced by its own rate (we send 1 req/source/day); HN's Algolia has no documented limit. One tuple, one default, not a config knob. |
| Circuit-breaker state machine | never | §0a Demotes row: "per-source failure flag is enough." The `runs` table *is* the flag — `failure_streak > N` surfaces in `status`/`doctor`. No in-memory state, no timer-based cool-downs, no manual reset. |
| structlog → OpenTelemetry bridge | never | Single-user tool. No distributed system, no spans. OTEL is SaaS observability. |
| Prometheus / metrics HTTP endpoint | never | Same reason. `runs` table queried from `status` is the metrics surface. |
| Alerting on failure streak (email / SMS / Slack) | Phase 13 if ever | Sentry or a GH Actions workflow reading `runs` is the right shape; both depend on Phase 13's secret-loading. |
| Replacing `print()` in `cli.py` / `deepdive.py` | never | `.claude/CLAUDE.md` explicitly carves these out. CLI stdout is the UX contract. |
| `_LogStream` rewrite against structlog in scheduled mode | Phase 13 | `cli.py:52-69` redirects `sys.stdout` into the stdlib logger. Still works fine because structlog's stdlib bridge is in the pipeline — log lines come out the same handler. Rewriting the redirect around `structlog.processors.CallsiteParameterAdder` is cosmetic. |
| Dashboard "Pipeline health" widget | Phase 14 (UX polish) | Belongs with the multi-page routing cleanup, not plumbing. `storage.last_run` / `failure_streak` are already callable from `web/cache.py` when that phase lands. |
| Async HTTP / `httpx.AsyncClient` retries | never | §6 demotes async entirely. The retry helper is sync and stays sync. |
| Postgres-aware `runs` sharding / partitioning | never | §12 drops Postgres. SQLite + one `runs` row per source per day = ~1500 rows/year. No partitioning ever needed. |
| Retries on Gmail `_get_service` OAuth | never | Auth failures must surface immediately; retrying three times before telling the user their token expired is worse UX than failing once. |
| Retries on `feedparser` *parse* errors | never | The retry wraps the HTTP round-trip only. A feed that returns valid XML-but-garbage is a real failure, not a transient one. |

## Effort estimate

- **1 engineering day** per `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 13. Broken down:
  - structlog wiring (`observability/logging.py` + `cli.py`/`web/app.py` callback hooks + `extra={...}` → kwargs sweep): ~2h. Mechanical.
  - Retry helper + the four wire-up sites: ~2h. Helper is <50 LOC with its test; wiring is 4 × ~10 LOC.
  - `0002_runs_table.sql` + `record_run` / `last_run` / `failure_streak` on `SqliteStorage` + Protocol: ~1.5h. The SQL is trivial; `failure_streak` is a single SELECT with `WHERE error IS NOT NULL ORDER BY id DESC LIMIT (streak+1)` short-circuit.
  - `cli.pipeline()` wrap-with-timer + `status`/`doctor` extensions: ~1h.
  - Tests (6 files): ~1.5h.
- Critical path: the structlog pipeline decision between `structlog.stdlib.BoundLogger` vs native `structlog.BoundLogger`. Pick **stdlib-backed** so deps that log via `logging.getLogger` flow in without per-dep wiring. The trade-off (slightly heavier per-call overhead) is invisible at our log volume (~100 lines/run).
- Secondary: the "fails twice then succeeds" integration tests. The vcrpy replay model assumes a 1:1 request:cassette mapping; simulating a transient failure requires either (a) recording three cassettes and cycling, or (b) monkeypatching `retry`'s `time.sleep` + the transport to raise twice. (b) is what we do — noted in the plan explicitly to save future-you a half-hour.
- Tertiary: auditing every `log.X("event", extra={"...})` call. `grep -rn 'extra=' startup_radar/` is the ground truth — target for final check is zero matches.
- Tag at end: `phase-11`.

## Prerequisites

- ✅ Phase 10 (`phase-10` tag pending). `Storage` Protocol + migrator infra in place; adding `record_run` / `last_run` / `failure_streak` extends an already-working seam.
- ✅ `make ci` green at start. Working tree clean.
- ✅ Phase 5's pydantic `AppConfig` — `cfg.network.timeout_seconds` is a straightforward sub-model addition.
- One new runtime dep: `structlog>=24.0`. No dev deps. No new GH Actions secrets. No MCP servers.
- No change to the `data` branch schema — new `runs` table is auto-populated by the next daily run; existing DB pulls still work because `0002_runs_table.sql` is idempotent.
- ⚠️ Heads-up: `pytest-cov`'s strict-markers config already covers the new test files. `tests/integration/test_source_*.py` additions land behind `-m integration` but don't require the vcrpy cassette record dance — monkeypatching `time.sleep` + transport is enough.

---

## 1. Files to change

| Path | Action | Notes |
|---|---|---|
| `pyproject.toml` | edit | Append `structlog>=24.0` to `[project.dependencies]`. No other adds. `[tool.coverage.run].omit` stays unchanged (new `observability/` module is covered). |
| `startup_radar/observability/__init__.py` | **create** | Empty module marker. |
| `startup_radar/observability/logging.py` | **create** | `configure_logging(json: bool) -> None` + `get_logger(name: str)` thin wrapper. ~50 lines including the processor chain. |
| `startup_radar/sources/_retry.py` | **create** | `retry(fn, *, attempts=3, backoff=(1, 2, 4), on=(…))` + `with_retry(...)` decorator alias. ~40 LOC. The underscore prefix is deliberate — this is private to `sources/`, not a public helper. |
| `startup_radar/config/schema.py` | edit | Add `class NetworkConfig(BaseModel): timeout_seconds: int = 10` + attach `network: NetworkConfig = NetworkConfig()` to `AppConfig`. `extra="forbid"` stays inherited. |
| `startup_radar/cli.py` | edit | (a) At `app` callback (currently none — add `@app.callback(invoke_without_command=False)` returning None), call `configure_logging(json=_json_logs())` where `_json_logs()` returns `os.getenv("STARTUP_RADAR_LOG_JSON") == "1" or os.getenv("CI") == "1"`. (b) In `pipeline()`, wrap each `source.fetch` call in start/end timer + try/except + `storage.record_run(...)`. (c) Extend `_status()` output with per-source health block. (d) Extend `_doctor()` with failure-streak warning. (e) Replace `log = logging.getLogger(...)` at any remaining call-site with `log = structlog.get_logger(__name__)`. |
| `startup_radar/sources/rss.py` | edit | Wrap `feedparser.parse(feed_url)` call at line 106 in `retry(...)`. Convert `log.warning(..., extra={...})` at lines 99-102 to kwarg form. Keep the outer try/except/return `[]` contract. |
| `startup_radar/sources/hackernews.py` | edit | Wrap the `requests.get(...)` call at lines 61-70 in `retry(...)`. Convert `log.warning(..., extra={...})` at 74-77 to kwargs. |
| `startup_radar/sources/sec_edgar.py` | edit | Wrap `requests.get(EDGAR_SEARCH_URL, …)` at line 79 in `retry(...)`. Convert `log.warning` at line 83 to kwargs. |
| `startup_radar/sources/gmail.py` | edit | Wrap the three idempotent Gmail API GETs (`labels().list`, `messages().list`, per-message `.get`) in `retry(...)`. `_get_service` stays unwrapped. Convert four `log.warning(..., extra={...})` call-sites to kwargs. |
| `startup_radar/storage/base.py` | edit | Add three Protocol methods: `record_run`, `last_run`, `failure_streak`. Types per the SQL shape. |
| `startup_radar/storage/sqlite.py` | edit | Implement `record_run` (single INSERT inside `with self._conn:`), `last_run` (single SELECT), `failure_streak` (SELECT with limit). Convert module-level `log = logging.getLogger(__name__)` to `structlog.get_logger(__name__)`. Convert the `log.info("storage.migrated", extra={...})` at line 45-48 to kwargs. |
| `startup_radar/storage/migrator.py` | edit | `log.exception("migration.failed", extra={...})` + `log.info("migration.applied", extra={...})` both collapse to kwargs. One-line change per call. |
| `startup_radar/storage/migrations/0002_runs_table.sql` | **create** | ~15 lines SQL per §2.5. Ends without a trailing `PRAGMA user_version`; the migrator sets it. |
| `startup_radar/web/app.py` | edit | Before `st.set_page_config(...)` at line 20, call `configure_logging(json=os.getenv("STARTUP_RADAR_LOG_JSON") == "1")`. No `CI=1` fallback here — when the dashboard runs under `streamlit run` in CI (AppTest fixtures), JSON would confuse the test harness; explicit env-var only. |
| `tests/unit/test_retry.py` | **create** | ~80 lines. Five tests: happy path, fails-twice-succeeds, exhausts-all-attempts, backoff-sleep-times-monkeypatched, only-retries-on-listed-exceptions. |
| `tests/unit/test_observability_logging.py` | **create** | ~60 lines. Captures log output via `capsys` (pretty) and `structlog.testing.capture_logs()` (JSON path). Asserts on structured fields, never on formatted strings, per `.claude/rules/testing.md`. |
| `tests/unit/test_storage_runs.py` | **create** | ~70 lines. Round-trip `record_run` + `last_run` + `failure_streak`; verifies `failure_streak` counts from newest row and stops at first `error IS NULL`. |
| `tests/unit/test_storage_migrator.py` | edit | Add one test: `test_migrate_0001_to_0002_preserves_data` — seed `startups` at v=1, run migrator with a migrations-dir containing both 0001 and 0002, assert v=2 and row count unchanged. |
| `tests/unit/test_cli_status.py` | edit | Extend `test_status_reports_zero_rows_on_fresh_db` with an assertion for the `Per-source health:` block. Add `test_status_shows_failure_streak` — seed two failed `runs` rows for `rss`, expect `rss` line to mention "2 failures". |
| `tests/unit/test_cli_doctor.py` | edit | Add `test_doctor_warns_on_failure_streak` — seed three failed `runs` rows for `hackernews`, invoke `doctor`, assert a `⚠` line appears and exit-code stays 0 (transient-network tolerance). |
| `tests/integration/test_source_rss.py` | edit | Add `test_fetch_retries_then_succeeds` — monkeypatch `time.sleep` to a no-op + patch `feedparser.parse` to raise twice then return a valid cassette body, confirm 2 retries fired. |
| `tests/integration/test_source_hackernews.py` | edit | Same shape; patch `requests.get` to raise `requests.ConnectionError` twice then return the recorded response. |
| `tests/integration/test_source_sec_edgar.py` | edit | Same shape. |
| `tests/integration/test_source_gmail.py` | edit | Same shape, patched against `service.users().messages().list`. |
| `.claude/rules/observability.md` | edit | Append one bullet: "Must: call `startup_radar.observability.logging.configure_logging(json=...)` once per process at startup. Never re-configure; never call `logging.basicConfig`." Remove the "(Phase 13 dependency)" parenthetical from bullet 1 — structlog lands here. |
| `.claude/CLAUDE.md` | edit | (a) Gotcha: "Set `STARTUP_RADAR_LOG_JSON=1` for JSON logs locally; `CI=1` auto-selects JSON. Never call `logging.basicConfig` — structlog's stdlib bridge is pre-configured." (b) Repo-layout tree: add `startup_radar/observability/logging.py` row. (c) Bump the Streamlit multi-page-split annotation from "Phase 11" (wrong — that landed Phase 9) to remove the stale note. |
| `docs/PRODUCTION_REFACTOR_PLAN.md` | edit | §0a row 13 → ✅ with `phase-11` tag + commit SHA. §4.3 Observability bullet `structlog with JSON in prod, pretty in dev` → ticked; Sentry bullet stays open for Phase 13. §4.4 Retries/timeouts — tick the retry line; Circuit-breaker bullet explicitly crossed out with footnote pointing at §0a Demotes row ("per-source failure flag is enough"). |
| `README.md` | edit | "Development" section gains a 2-line block: "Set `STARTUP_RADAR_LOG_JSON=1` for JSON log output; otherwise logs render pretty with color. Logs from all sources and the migrator share the same stream." |
| `docs/plans/phase-11.md` | **create** | This document. |

### Files explicitly NOT to touch

- `startup_radar/sources/base.py` — ABC stays thin. Retries live at call-sites, not on the base class.
- `startup_radar/sources/registry.py` — no new source, no registry change.
- `startup_radar/storage/migrations/0001_initial.sql` — untouched; `0002_runs_table.sql` is additive.
- `startup_radar/cli.py` `print()` call-sites — left in place. CLI stdout IS the UX.
- `startup_radar/research/deepdive.py` — CLI-adjacent tier; `print()` allowed per CLAUDE.md; not a Phase 11 concern.
- `startup_radar/web/pages/*.py` — dashboard health strip deferred to Phase 14.
- `sinks/google_sheets.py` — no logging call-sites to migrate.
- `.github/workflows/daily.yml` — confirmed compatible: `CI=1` is set by default on runners; JSON logs stream to the workflow log capture cleanly.
- `tests/unit/test_storage_sqlite.py` — already covers `insert_startups` / `is_processed`; new `runs`-table tests live in their own file to keep file-per-concern.
- `config.yaml` / `config.example.yaml` — `cfg.network.timeout_seconds` has a default; existing configs stay valid.

---

## 2. New/changed file shapes

### 2.1 `startup_radar/observability/logging.py`

```python
"""structlog pipeline. One entry point: ``configure_logging(json: bool)``.

Called once per process — CLI ``@app.callback`` and dashboard ``web/app.py``
shell. Never call ``logging.basicConfig`` anywhere else; structlog's stdlib
bridge owns the root logger.

JSON mode when ``CI=1`` or ``STARTUP_RADAR_LOG_JSON=1``. Pretty
``ConsoleRenderer`` locally — color-coded, aligned, human-scannable.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(*, json: bool) -> None:
    """Configure structlog + the stdlib root logger. Idempotent."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if json
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging through the same pipeline so google-api-python-client,
    # urllib3, feedparser all end up in one stream.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=renderer,
            foreign_pre_chain=shared_processors,
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def get_logger(name: str):  # thin re-export; keeps call-sites ignorant of structlog import
    return structlog.get_logger(name)
```

Notes:
- `cache_logger_on_first_use=True` — first `get_logger(__name__)` call binds the proxy; subsequent calls skip the processor-chain compile.
- `ProcessorFormatter` with `foreign_pre_chain` is the canonical way to format stdlib logs through structlog processors. Without it, `urllib3`'s `connectionpool` logs come out unformatted.
- `json=False` renders ANSI colors; tests that assert on output strip via `structlog.testing.capture_logs()` which bypasses the renderer entirely.

### 2.2 `startup_radar/sources/_retry.py`

```python
"""Tiny retry helper for source network calls. ~40 LOC, no deps.

Rationale: ``docs/CRITIQUE_APPENDIX.md`` §7 rules out ``tenacity`` /
``backoff`` — the general-purpose retry libraries carry more surface area
than our three-line needs. Exponential backoff on a fixed tuple, stops on
a fixed exception list, logs at WARNING on each retry. Nothing more.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from startup_radar.observability.logging import get_logger

T = TypeVar("T")

_DEFAULT_BACKOFF: tuple[float, ...] = (1.0, 2.0, 4.0)
_DEFAULT_ATTEMPTS: int = 3

log = get_logger(__name__)


def retry(
    fn: Callable[[], T],
    *,
    attempts: int = _DEFAULT_ATTEMPTS,
    backoff: tuple[float, ...] = _DEFAULT_BACKOFF,
    on: tuple[type[BaseException], ...] = (Exception,),
    context: dict[str, object] | None = None,
) -> T:
    """Call ``fn()``; on any exception in ``on`` retry up to ``attempts-1`` times.

    ``backoff[i]`` is the sleep before the ``i+1``-th attempt (0-indexed).
    If ``backoff`` is shorter than ``attempts-1``, the last value repeats.
    ``context`` is merged into each retry log line.
    """
    assert attempts >= 1
    ctx = context or {}
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except on as e:
            last = e
            if i == attempts - 1:
                break
            delay = backoff[min(i, len(backoff) - 1)]
            log.warning(
                "retry.backoff",
                attempt=i + 1,
                of=attempts,
                sleep_s=delay,
                err=type(e).__name__,
                **ctx,
            )
            time.sleep(delay)
    assert last is not None
    raise last
```

Notes:
- `context` is how sources pass `source=<name>` / `feed=<feed.name>` into the retry log without polluting the signature.
- Tests monkeypatch `time.sleep` to a no-op. The `last is not None` assertion is belt-and-suspenders — the loop only reaches the outer `raise` after at least one `except`.
- `on=(Exception,)` default is intentionally loose for simplicity. Sources pass narrower tuples (e.g. `(requests.RequestException, TimeoutError)`) where it matters; the RSS site uses the default because `feedparser` raises a zoo of types.

### 2.3 Source wiring example — `sources/hackernews.py` diff

```diff
 import requests

+from startup_radar.config import AppConfig
 from startup_radar.models import Startup
 from startup_radar.parsing.funding import AMOUNT_RE, COMPANY_SUBJECT_RE, STAGE_RE
 from startup_radar.sources.base import Source
+from startup_radar.sources._retry import retry

 ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"

-log = logging.getLogger(__name__)
+from startup_radar.observability.logging import get_logger
+
+log = get_logger(__name__)


 class HackerNewsSource(Source):
     name = "Hacker News"
     enabled_key = "hackernews"

     def fetch(self, cfg: AppConfig, storage=None) -> list[Startup]:
         hn_cfg = cfg.sources.hackernews
         if not hn_cfg.enabled:
             return []
+        timeout = cfg.network.timeout_seconds
         …
         for query in queries:
             try:
-                resp = requests.get(
-                    ALGOLIA_URL,
-                    params={...},
-                    timeout=15,
-                )
+                resp = retry(
+                    lambda: requests.get(
+                        ALGOLIA_URL,
+                        params={...},
+                        timeout=timeout,
+                    ),
+                    on=(requests.RequestException, TimeoutError),
+                    context={"source": self.name, "query": query},
+                )
                 resp.raise_for_status()
                 hits = resp.json().get("hits", [])
             except Exception as e:
-                log.warning(
-                    "source.fetch_failed",
-                    extra={"source": self.name, "query": query, "err": str(e)},
-                )
+                log.warning(
+                    "source.fetch_failed",
+                    source=self.name,
+                    query=query,
+                    err=str(e),
+                )
                 continue
```

RSS, EDGAR, Gmail follow the same pattern. Gmail has three wrap sites (labels list, messages list, per-message get); the `_get_service` call at line 46 stays unwrapped per the rationale above.

### 2.4 `startup_radar/storage/migrations/0002_runs_table.sql`

```sql
-- 0002_runs_table.sql — per-source run telemetry.
-- One row per (source, invocation) written by cli.pipeline() via
-- Storage.record_run(...). Queried by Storage.last_run / failure_streak.
-- Idempotent over pre-Phase-11 DBs via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    items_fetched INTEGER,
    items_kept INTEGER,
    error TEXT,
    user_version_at_run INTEGER
);

CREATE INDEX IF NOT EXISTS idx_runs_source_id
    ON runs(source, id DESC);
```

`user_version_at_run` is cheap insurance — when a future schema change lands and we need to answer "which runs ran under the old schema?" we already have the answer. No trailing `PRAGMA user_version`; the migrator sets it.

### 2.5 `Storage` Protocol additions (`storage/base.py`)

```python
    # --- runs / telemetry (Phase 11) ---
    def record_run(
        self,
        source: str,
        *,
        started_at: str,
        ended_at: str,
        items_fetched: int,
        items_kept: int,
        error: str | None,
        user_version_at_run: int,
    ) -> int: ...

    def last_run(self, source: str) -> dict | None: ...

    def failure_streak(self, source: str) -> int: ...
```

### 2.6 `SqliteStorage` method bodies (`storage/sqlite.py`)

```python
    def record_run(
        self,
        source: str,
        *,
        started_at: str,
        ended_at: str,
        items_fetched: int,
        items_kept: int,
        error: str | None,
        user_version_at_run: int,
    ) -> int:
        with self._conn:
            cur = self._conn.execute(
                """INSERT INTO runs
                   (source, started_at, ended_at, items_fetched, items_kept,
                    error, user_version_at_run)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (source, started_at, ended_at, items_fetched, items_kept,
                 error, user_version_at_run),
            )
            return int(cur.lastrowid or 0)

    def last_run(self, source: str) -> dict | None:
        row = self._conn.execute(
            """SELECT id, source, started_at, ended_at, items_fetched, items_kept,
                      error, user_version_at_run
               FROM runs WHERE source = ? ORDER BY id DESC LIMIT 1""",
            (source,),
        ).fetchone()
        if row is None:
            return None
        cols = ("id", "source", "started_at", "ended_at", "items_fetched",
                "items_kept", "error", "user_version_at_run")
        return dict(zip(cols, row, strict=True))

    def failure_streak(self, source: str) -> int:
        # Count consecutive rows with error IS NOT NULL, newest-first, stop
        # at first success. Short-circuits — we never need more than the
        # streak+1 rows back.
        streak = 0
        for (err,) in self._conn.execute(
            "SELECT error FROM runs WHERE source = ? ORDER BY id DESC", (source,),
        ):
            if err is None:
                break
            streak += 1
        return streak
```

### 2.7 `cli.pipeline()` diff (retry/record-run wrap)

```diff
+from startup_radar.observability.logging import configure_logging, get_logger
+
+log = get_logger(__name__)

 def pipeline() -> int:
     …
     cfg = load_config()
     storage = load_storage(cfg)
+    uv_at_run = storage.user_version()

     try:
         all_startups: list[Startup] = []
         for key, source in SOURCES.items():
             sub_cfg = getattr(cfg.sources, key, None)
             if sub_cfg is None or not getattr(sub_cfg, "enabled", False):
                 continue
             print(f"\n[{source.name}] Fetching...")
+            started_at = datetime.utcnow().isoformat()
+            err_repr: str | None = None
+            found: list[Startup] = []
+            try:
-            found = source.fetch(cfg, storage=storage)
+                found = source.fetch(cfg, storage=storage)
+            except Exception as e:  # defence in depth — sources already catch
+                err_repr = repr(e)
+                log.exception("source.unhandled", source=source.name)
+            finally:
+                storage.record_run(
+                    source.name,
+                    started_at=started_at,
+                    ended_at=datetime.utcnow().isoformat(),
+                    items_fetched=len(found),
+                    items_kept=len(found),  # "kept" = same as fetched here; refined post-dedup below
+                    error=err_repr,
+                    user_version_at_run=uv_at_run,
+                )
             print(f"  {len(found)} candidate(s)")
             all_startups.extend(found)
```

Note: `items_kept` at record-time is the per-source fetched count, not the post-dedup global count. Refining it would require a second UPDATE pass after the dedup loop — plumbing not worth the cost. The dashboard / `status` cares about "is this source alive" (did we fetch anything, did it error), and the distinction between `fetched` vs `kept` is answered there.

### 2.8 `status` output extension

```diff
     print(
         f"DB rows:        startups={db_counts['startups']}  "
         f"job_matches={db_counts['job_matches']}  connections={db_counts['connections']}"
     )
+    print()
+    print("Per-source health:")
+    for name in ("rss", "hackernews", "sec_edgar", "gmail"):
+        sub = getattr(cfg.sources, name, None)
+        if sub is None or not getattr(sub, "enabled", False):
+            print(f"  {name:<12} (disabled)")
+            continue
+        lr = storage.last_run(name)
+        streak = storage.failure_streak(name)
+        age = _format_age(...)  # compute from lr['ended_at']
+        marker = "⚠" if streak > 2 else "✓" if lr and lr["error"] is None else "–"
+        print(f"  {marker} {name:<12} last run {age}  |  failure streak {streak}")
     return 0
```

### 2.9 `doctor` warning extension

```diff
         for key, source in SOURCES.items():
             sub = getattr(cfg.sources, key, None)
             if sub is None or not getattr(sub, "enabled", False):
                 checks.append(("⚠", f"source.{key}", "disabled in config"))
                 continue
             try:
                 ok, detail = source.healthcheck(cfg, network=network)
                 mark = "✓" if ok else "✗"
                 checks.append((mark, f"source.{key}", detail))
                 if not ok:
                     fails += 1
             except Exception as e:
                 checks.append(("✗", f"source.{key}", f"healthcheck raised: {e}"))
                 fails += 1
+            streak = storage.failure_streak(key)
+            if streak > 2:
+                checks.append(("⚠", f"source.{key}.streak", f"{streak} consecutive failed runs"))
+                # streak alone does NOT increment `fails` — transient network on a single-user tool.
```

### 2.10 `tests/unit/test_retry.py` (skeleton)

```python
"""Retry helper tests. All hermetic — ``time.sleep`` is monkeypatched."""

from __future__ import annotations

import pytest

from startup_radar.sources._retry import retry


def test_returns_on_first_success(monkeypatch) -> None:
    calls = {"n": 0}

    def fn() -> int:
        calls["n"] += 1
        return 42

    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert retry(fn) == 42
    assert calls["n"] == 1


def test_retries_twice_then_succeeds(monkeypatch) -> None:
    calls = {"n": 0}

    def fn() -> int:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("flaky")
        return 7

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda d: sleeps.append(d))

    assert retry(fn) == 7
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_exhausts_attempts_then_raises(monkeypatch) -> None:
    def fn() -> int:
        raise TimeoutError("forever")

    monkeypatch.setattr("time.sleep", lambda *_: None)
    with pytest.raises(TimeoutError):
        retry(fn, attempts=3)


def test_only_retries_listed_exceptions(monkeypatch) -> None:
    def fn() -> int:
        raise ValueError("not retryable")

    monkeypatch.setattr("time.sleep", lambda *_: None)
    with pytest.raises(ValueError):
        retry(fn, on=(ConnectionError,), attempts=3)


def test_backoff_tuple_extends_by_last_value(monkeypatch) -> None:
    calls = {"n": 0}

    def fn() -> int:
        calls["n"] += 1
        raise ConnectionError

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda d: sleeps.append(d))

    with pytest.raises(ConnectionError):
        retry(fn, attempts=5, backoff=(0.1, 0.2))

    assert sleeps == [0.1, 0.2, 0.2, 0.2]
    assert calls["n"] == 5
```

### 2.11 `tests/unit/test_observability_logging.py` (skeleton)

```python
"""structlog pipeline tests. Use structlog.testing.capture_logs() for the
JSON path and capsys for the pretty path."""

from __future__ import annotations

import json
import logging

import structlog

from startup_radar.observability.logging import configure_logging, get_logger


def test_json_mode_emits_json_object(capsys) -> None:
    configure_logging(json=True)
    log = get_logger("t")
    log.info("thing.happened", x=1, y="two")

    err = capsys.readouterr().err.strip()
    assert err, "expected a JSON log line"
    record = json.loads(err)
    assert record["event"] == "thing.happened"
    assert record["level"] == "info"
    assert record["x"] == 1
    assert record["y"] == "two"
    assert "timestamp" in record


def test_pretty_mode_renders_event_and_fields(capsys) -> None:
    configure_logging(json=False)
    log = get_logger("t")
    log.info("thing.happened", x=1)
    err = capsys.readouterr().err
    assert "thing.happened" in err
    assert "x=1" in err


def test_contextvars_propagate(capsys) -> None:
    configure_logging(json=True)
    log = get_logger("t")
    with structlog.contextvars.bound_contextvars(source="rss"):
        log.info("source.fetch")
    record = json.loads(capsys.readouterr().err.strip())
    assert record["source"] == "rss"


def test_stdlib_logger_flows_through(capsys) -> None:
    configure_logging(json=True)
    logging.getLogger("urllib3").info("adapter.send", extra={"pool": 1})
    # Not asserting on ``extra``-as-kwarg because stdlib's ``extra`` goes through
    # foreign_pre_chain; we just confirm the line made it to stderr as JSON.
    err = capsys.readouterr().err.strip()
    assert err and json.loads(err)["event"] == "adapter.send"
```

### 2.12 `tests/unit/test_storage_runs.py` (skeleton)

```python
"""record_run / last_run / failure_streak round-trip."""

from __future__ import annotations

from pathlib import Path

from startup_radar.storage.sqlite import SqliteStorage


def _mk(tmp_path: Path) -> SqliteStorage:
    s = SqliteStorage(tmp_path / "x.db")
    s.migrate_to_latest()
    return s


def test_record_and_last_run(tmp_path: Path) -> None:
    s = _mk(tmp_path)
    s.record_run(
        "rss", started_at="2026-04-19T12:00:00", ended_at="2026-04-19T12:00:02",
        items_fetched=5, items_kept=3, error=None, user_version_at_run=2,
    )
    lr = s.last_run("rss")
    assert lr is not None
    assert lr["items_fetched"] == 5
    assert lr["error"] is None


def test_failure_streak_counts_from_newest(tmp_path: Path) -> None:
    s = _mk(tmp_path)
    for err in (None, "boom", "boom"):  # inserted in order; streak starts at newest
        s.record_run(
            "hackernews", started_at="t", ended_at="t",
            items_fetched=0, items_kept=0, error=err, user_version_at_run=2,
        )
    assert s.failure_streak("hackernews") == 2


def test_failure_streak_resets_on_success(tmp_path: Path) -> None:
    s = _mk(tmp_path)
    for err in ("boom", "boom", None):
        s.record_run(
            "sec_edgar", started_at="t", ended_at="t",
            items_fetched=0, items_kept=0, error=err, user_version_at_run=2,
        )
    assert s.failure_streak("sec_edgar") == 0


def test_last_run_none_for_unknown_source(tmp_path: Path) -> None:
    s = _mk(tmp_path)
    assert s.last_run("gmail") is None
    assert s.failure_streak("gmail") == 0
```

---

## 3. Execution order

1. **Branch**: stay on `refactor/v2`. Working tree clean, `phase-10` tag in place.
2. **Dep bump** — `pyproject.toml`: append `structlog>=24.0` to `[project.dependencies]`, `uv lock`, `uv sync --all-extras`. Commit separately so the lockfile hop is isolated.
3. **Observability module** — create `startup_radar/observability/{__init__,logging.py}`; write `configure_logging` + `get_logger`. Run the `test_observability_logging.py` file alone (`uv run pytest tests/unit/test_observability_logging.py -q`) before anything else imports the module.
4. **Retry helper** — create `startup_radar/sources/_retry.py`; write `test_retry.py`; verify in isolation. ~40 LOC + test file. Commit.
5. **Config extension** — add `NetworkConfig` + `network` field to `AppConfig` schema, default `timeout_seconds=10`. Run `uv run startup-radar doctor` against an unmodified `config.yaml` — must still load (default fills in). Commit.
6. **Migration 0002** — create `0002_runs_table.sql` + extend `test_storage_migrator.py` with the data-preserving test. Run migrator tests in isolation. No source-code changes yet. Commit.
7. **Storage methods** — add `record_run` / `last_run` / `failure_streak` to Protocol + SqliteStorage. Write `test_storage_runs.py`. Commit.
8. **CLI callback + pipeline wrap** — add `@app.callback` that calls `configure_logging(...)`; extend `pipeline()` with the per-source `record_run` wrap. Verify against a tmp-path DB: `uv run startup-radar run` writes one `runs` row per enabled source.
9. **Source wiring** — apply the retry + `extra={...}` → kwarg edits to all four sources. Run `uv run pytest tests/integration -q` to confirm the existing cassette-backed tests still pass (retries fire zero times on a clean cassette, so the wiring is invisible to them).
10. **Integration "retries-then-succeeds" tests** — extend each of the four `test_source_*.py` files with the monkeypatched-transient-failure test. Confirm each exercises 2 retries.
11. **`status` / `doctor` extensions** — implement the output changes + extend their unit tests.
12. **Storage + migrator log-call migration** — convert the `log.info("storage.migrated", extra={...})` and migrator call-sites to kwargs. Confirm `grep -rn 'extra={' startup_radar/` returns empty.
13. **Manual QA** —
    - `uv run startup-radar run` → confirm pretty logs + `runs` rows inserted; `sqlite3 startup_radar.db "SELECT source, error FROM runs ORDER BY id DESC LIMIT 10"` shows one row per source.
    - `STARTUP_RADAR_LOG_JSON=1 uv run startup-radar run` → confirm JSON lines on stderr.
    - `uv run startup-radar status` → new `Per-source health:` block renders.
    - `uv run startup-radar doctor` → warn line appears when you hand-insert three failed `runs` rows.
    - `uv run startup-radar serve` → dashboard renders; no log-config collisions with Streamlit's own logging.
    - Pull the `data` branch DB and run `startup-radar run` against it — confirm the migrator applies 0002 over the already-populated DB without data loss.
14. **`make ci`** — all green. Pay attention to mypy on `Storage` Protocol additions and the new retry helper's TypeVar.
15. **Docs pass** — `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 13 + §4.3 tick; `.claude/rules/observability.md`; `.claude/CLAUDE.md` gotcha + layout tree; `README.md` "Development".
16. **Tag** — `git tag phase-11 && git push origin phase-11`. User-driven per CLAUDE.md's "do not delegate commits" rule.

---

## 4. Rollback plan

Multi-commit phase. Revert strategy by severity:

- **Caught in CI before push**: `git reset --soft <phase-11-parent>` + re-work. `uv.lock` delta for `structlog` is clean to throw away.
- **Caught after local merge, pre-tag**: `git revert <merge-commit>`. The `0002_runs_table.sql` file disappears on revert, but `PRAGMA user_version` stays at 2 — which is fine because 0002 is pure-additive: reverted code reading the same DB just ignores the `runs` table.
- **Caught after push + tag**: `git revert` the range, `git tag -d phase-11`, `git push --delete origin phase-11`. No DB surgery needed.
- **Data-integrity escape hatch**: the migration never mutates existing tables. Worst case, a bad `record_run` call leaves a garbage row in `runs` — `DELETE FROM runs WHERE source = ?` is safe; no FK constraints reference the table.
- **structlog misconfiguration locks up logs**: `configure_logging` is idempotent — the root-logger rewire is the last thing it does. If a process comes up with no log output, revert `cli.py`'s callback to a no-op and raise an issue; the underlying `get_logger` fallback renders to stderr via stdlib defaults.

No `git mv` this phase; every edit is in-place or additive. Revert is clean.

---

## 5. Exit criteria

Every bullet independently verifiable.

- [ ] `structlog>=24.0` is in `pyproject.toml` `[project.dependencies]`. `uv.lock` reflects it.
- [ ] `startup_radar/observability/logging.py` exists and exports `configure_logging(json: bool)` and `get_logger(name)`.
- [ ] `startup_radar/observability/__init__.py` exists (empty marker).
- [ ] `startup_radar/sources/_retry.py` exists, ≤ 60 LOC (ignoring docstring + blank lines), and exports `retry(...)`.
- [ ] `startup_radar/storage/migrations/0002_runs_table.sql` exists; `PRAGMA user_version` equals 2 after `migrate_to_latest()` on a fresh DB.
- [ ] `grep -rn "extra={" startup_radar/` returns empty (all call-sites migrated to structlog kwargs).
- [ ] `grep -rn "import logging" startup_radar/` still returns matches only in `cli.py` (keeps the scheduled-mode file handler) — no other library module uses stdlib `logging` directly.
- [ ] `Storage` Protocol in `storage/base.py` exposes `record_run`, `last_run`, `failure_streak`.
- [ ] `SqliteStorage` implements all three; unit tests (`test_storage_runs.py`) pass.
- [ ] `cli.app` has a `@app.callback` that calls `configure_logging(json=os.getenv("STARTUP_RADAR_LOG_JSON") == "1" or os.getenv("CI") == "1")`.
- [ ] `startup_radar/web/app.py` calls `configure_logging(json=os.getenv("STARTUP_RADAR_LOG_JSON") == "1")` before `st.set_page_config`.
- [ ] Each of `rss.py`, `hackernews.py`, `sec_edgar.py`, `gmail.py` imports `from startup_radar.sources._retry import retry` and uses it around the intended network call(s).
- [ ] `uv run startup-radar run` writes exactly one `runs` row per enabled source per invocation. Verified via `sqlite3 startup_radar.db "SELECT source, error FROM runs ORDER BY id DESC LIMIT 10"`.
- [ ] `uv run startup-radar status` output includes a `Per-source health:` block with last-run age and failure streak per enabled source.
- [ ] `uv run startup-radar doctor` emits a `⚠ source.<name>.streak` line when `failure_streak > 2`; exit code stays 0 (warnings don't fail doctor).
- [ ] `STARTUP_RADAR_LOG_JSON=1 uv run startup-radar run` streams valid JSON on stderr (one object per log call).
- [ ] `make ci` green. All of: `tests/unit/test_retry.py`, `test_observability_logging.py`, `test_storage_runs.py` pass. Extended `test_storage_migrator.py`, `test_cli_status.py`, `test_cli_doctor.py`, and the four `tests/integration/test_source_*.py` pass.
- [ ] Manual: pulling the `data`-branch DB and running `startup-radar run` applies 0002 cleanly, preserves existing rows, and begins populating `runs`.
- [ ] `.claude/rules/observability.md` has the new "must call `configure_logging` once" bullet, with the Phase 13 parenthetical on bullet 1 removed.
- [ ] `.claude/CLAUDE.md` has the `STARTUP_RADAR_LOG_JSON` Gotcha and the `observability/logging.py` layout row.
- [ ] `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 13 → ✅ with `phase-11` tag + commit SHA. §4.3's structlog bullet is ticked; Sentry bullet left open for Phase 13. §4.4's circuit-breaker line carries the "superseded — per-source failure flag sufficient" footnote.
- [ ] `README.md` "Development" mentions `STARTUP_RADAR_LOG_JSON`.
- [ ] Tag `phase-11` pushed (by the user).

---

## 6. Post-phase note

**Phase 12 (§0a row 14): Dockerfile (single image, optional).** With structlog + the `runs` table in place, a Dockerfile for the single-user deploy is straightforward — one `CMD ["startup-radar", "serve"]`, `STARTUP_RADAR_LOG_JSON=1` baked in, volume-mount the DB. The observability bridge means container logs are machine-readable by default.

**Phase 13 (§4.3 open line): Sentry.** The structlog chain from Phase 11 is the exact seam — add `sentry_sdk.integrations.logging.EventHandler` in front of the final renderer when `SENTRY_DSN` is set, and `log.error(...)` calls get a span. Zero call-site changes. `pydantic-settings` `.env` loading (also §4.3) is the other half — `SENTRY_DSN` becomes its first tenant, joining `STARTUP_RADAR_LOG_JSON` as the sanctioned log-facing env vars.

**Phase 14 (UX polish): dashboard "Pipeline health".** `storage.last_run` / `failure_streak` are already callable from `web/cache.py`; wrapping them in an `@st.cache_data(ttl=60)` helper and rendering a strip on page 1 is a half-day's work whenever it becomes annoying enough that per-source health isn't discoverable via `status` anymore.

**Also unlocked**: future sources that retry automatically without any base-class ceremony — just `from ._retry import retry` in the new `sources/foo.py` file and wrap the network call. The `source-implementer` subagent template should be updated to include the import + a retry-wrapped example; tracked as a follow-up to `.claude/subagents/source-implementer.md` but not a Phase 11 exit criterion (the phase scope is the four existing sources).
