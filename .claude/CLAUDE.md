# Startup Radar — Claude Context

Single-user Python tool that aggregates startup-funding signals from RSS, Hacker News, SEC EDGAR, and (optional) Gmail newsletters; filters by user criteria; serves a Streamlit dashboard with application tracking, warm-intro lookup, and AI-generated research briefs.

## Stack
- Python ≥3.10 (`pyproject.toml`); eventual target 3.11.
- Package manager: `uv` — `pyproject.toml` + `uv.lock` are the source of truth (Phase 2). Add deps via `uv add <pkg>`; never reintroduce `requirements.txt`.
- DB: SQLite, single file (`startup_radar.db`).
- Web: Streamlit (single-file `app.py`, ~1100 LOC; multi-page split in Phase 11).
- HTTP: `requests` today; migrating to `httpx` in Phase 13.
- Parsing: `feedparser`, `beautifulsoup4`.
- Configuration: `config.yaml` validated by pydantic `AppConfig` in `startup_radar/config/` (Phase 5).
- Secrets: `credentials.json`, `token.json`, `.env` — never commit, never read via shell.

## Repo layout
```
.
├── database.py                              # SQLite layer (33 fns; moves to startup_radar/storage/ Phase 10)
├── startup_radar/                           # the package (created Phase 3)
│   ├── cli.py                               # Typer CLI (Phase 4): run, serve, deepdive; `run --scheduled` is the cron entry
│   ├── models.py                            # @dataclass Startup, JobMatch
│   ├── filters.py                           # StartupFilter + JobFilter (moved from root in Phase 5)
│   ├── config/{schema,loader}.py            # pydantic AppConfig (Phase 5) — single source of truth for config.yaml
│   ├── parsing/{funding,normalize}.py       # AMOUNT_RE/STAGE_RE/COMPANY_*; normalize_company, dedup_key
│   ├── research/deepdive.py                 # AI research brief generator (moved from root in Phase 4)
│   ├── sources/                             # Source ABC + per-source subclasses
│   │   ├── base.py                          # Source ABC: name, enabled_key, fetch(cfg), healthcheck()
│   │   ├── registry.py                      # SOURCES: dict[str, Source]
│   │   └── {rss,hackernews,sec_edgar,gmail}.py
│   └── web/                                 # Streamlit dashboard (split Phase 9)
│       ├── app.py                           # ~80-line shell: page-config, config load, DB init, sidebar
│       ├── cache.py                         # @st.cache_data(ttl=60) wrappers around database.*
│       ├── state.py                         # session-state + widget key constants (collision-asserted at import)
│       ├── lookup.py                        # DuckDuckGo company lookup (hoisted DDGS import)
│       ├── connections.py                   # LinkedIn CSV → tier-1/tier-2 helpers (moved from repo root in Phase 9)
│       └── pages/{1_dashboard,2_companies,3_jobs,4_deepdive,5_tracker}.py
├── sinks/google_sheets.py
├── scheduling/                              # cron, launchd, Windows Task templates
├── backups/                                 # local tarballs from `startup-radar backup` (gitignored, Phase 6)
├── tests/unit/test_web_smoke.py             # Phase 9 — AppTest shell smoke + page discovery + state collision
├── tests/unit/{test_cli_backup,test_cli_doctor,test_cli_status}.py  # Phase 6 — resilience CLI tests
├── tests/integration/                       # Phase 8 — vcrpy cassette-backed per-source tests
├── docs/                                    # PRODUCTION_REFACTOR_PLAN, CRITIQUE_APPENDIX, AUDIT_FINDINGS, plans/phase-N
└── .claude/                                 # this directory — harness
```
Target layout (Phase 10+) lives in `docs/PRODUCTION_REFACTOR_PLAN.md` §3.1.

## Core invariants
- **Must:** every new HTTP call uses `timeout=` (or shared `httpx.Client` once it lands). `feedparser` is the exception — see `startup_radar/sources/rss.py` (sets `socket.setdefaulttimeout(20)` at module load).
- **Must:** every source subclasses `startup_radar.sources.base.Source`, sets `name` + `enabled_key`, and implements `fetch(cfg) -> list[Startup]`. Free-function `fetch(...)` is gone since Phase 3.
- **Must:** every source registers in `startup_radar/sources/registry.py`.
- **Must:** funding regexes (`AMOUNT_RE`, `STAGE_RE`, `COMPANY_SUBJECT_RE`, `COMPANY_INLINE_RE`) live ONLY in `startup_radar/parsing/funding.py`. Never re-introduce duplicates per source.
- **Must:** company-name normalization goes through `normalize_company` / `dedup_key` in `startup_radar/parsing/normalize.py`.
- **Never:** `print()` outside `startup_radar/cli.py`, `startup_radar/research/deepdive.py`, or `tests/` — use `logging.getLogger(__name__)`.
- **Never:** `os.getenv()` outside `startup_radar/config/` (Phase 13 adds `secrets.py` there for `.env` consumers).
- **Never:** edit `credentials.json`, `token.json`, `.env`, `uv.lock`, or `*.db` files.
- **Never:** reintroduce `requirements.txt` — `pyproject.toml` + `uv.lock` are authoritative since Phase 2.
- **Never:** add Postgres, alembic, async pipeline, or dashboard auth — out of scope per `docs/CRITIQUE_APPENDIX.md` §12.

## Common commands
```bash
make lint                        # ruff check
make format                      # ruff format (writes)
make format-check                # ruff format --check (no writes)
make test                        # pytest
make typecheck                   # mypy
make ci                          # lint + format-check + typecheck + test
make serve                       # uv run startup-radar serve
make run                         # uv run startup-radar run
uv run startup-radar run --scheduled      # cron/launchd mode (logs + 15-min timeout)
uv run startup-radar deepdive "Anthropic" # research brief .docx
uv run startup-radar status               # branch + version + last-run age + DB row counts
uv run startup-radar doctor [--network]   # env / config / credentials / source healthchecks
uv run startup-radar backup [--no-secrets] [--db-only] # local tar.gz of DB + config + OAuth
```

## Gotchas
- `data` branch (GH Actions DB store, Phase 7) — NEVER delete, rebase, or force-push from a developer machine. The daily workflow writes to it; the weekly GC workflow is the only sanctioned force-pusher. To pull the prod DB locally: `git fetch origin data:data && git checkout data -- startup_radar.db`.
- `feedparser` does NOT take a `timeout` kwarg — `startup_radar/sources/rss.py` uses `socket.setdefaulttimeout(20)` at module load.
- SEC EDGAR requires `User-Agent: Name email@example.com` header AND ≤10 req/s.
- Streamlit re-runs the entire script on every interaction — wrap DB reads in `@st.cache_data(ttl=60)` via `startup_radar/web/cache.py`. Writes invalidate immediately by calling `load_data.clear()` after the insert.
- Dashboard sidebar (Run-pipeline button + LinkedIn uploader) lives ONLY in `startup_radar/web/app.py` (the shell). Native multi-page runs the shell on every page render, so sidebar code in the shell appears on every page — do NOT duplicate into pages.
- Session-state / widget keys in `startup_radar/web/pages/*` go through `startup_radar/web/state.py` constants. `state.assert_no_collisions()` fires at import time; two constants pointing at the same string raise `AssertionError` before Streamlit loads.
- GH Actions DB persistence uses commit-to-`data`-branch (Phase 7) — see `docs/ops/data-branch.md`. The old `actions/cache`-keyed-by-`run_id` scheme is gone.
- OAuth scopes for Gmail (`gmail.readonly`) and Sheets (`spreadsheets`) are merged into a single `token.json` — Phase 0 fix.
- Dedup key strips legal suffixes (`inc`, `llc`, `corp`, `gmbh`, `labs`, etc.) — see `LEGAL_SUFFIX_RE` in `startup_radar/parsing/normalize.py`. Real failure mode is "OpenAI" vs "Open AI Inc.", not whitespace.
- `parse_amount_musd("$2.5M") -> 2.5` from `startup_radar/parsing/funding.py` is the canonical amount parser — `startup_radar/filters.py` uses it (the duplicate `_parse_amount_musd` retired in Phase 5).
- CLI entry-point is registered via `[project.scripts]` in `pyproject.toml` and the `startup_radar.cli:app` shim — `uv sync --all-extras` refreshes it after edits to `cli.py` are not needed (editable install), but adding/removing commands does require a re-sync to refresh the `startup-radar` script wrapper.
- Version is derived by `setuptools-scm` from the git tag history (`phase-*` tags yield dev-style versions; `fallback_version = "0.1.0"` for source tarballs).
- vcrpy cassettes live in `tests/fixtures/cassettes/<source>/`. `CI=1` sets `record_mode=none` (missing cassette → test fails loud). Locally `record_mode=once` records on first run. Re-record by deleting the yaml + rerunning the test. EDGAR cassettes scrub User-Agent to `startup-radar-test`; don't commit a real email.

## @import references
For source-author conventions: @.claude/rules/sources.md
For storage/DB conventions: @.claude/rules/storage.md
For Streamlit conventions: @.claude/rules/dashboard.md
For logging/observability: @.claude/rules/observability.md
For test conventions: @.claude/rules/testing.md
For overall refactor plan: @docs/PRODUCTION_REFACTOR_PLAN.md
For critique/calibration: @docs/CRITIQUE_APPENDIX.md
For Phase 1 plan (this harness): @docs/plans/phase-1.md

## Subagents
- `source-implementer` — scaffold a new data source under `startup_radar/sources/` (Source subclass + registry entry).
- `filter-tuner` — diagnose `filters.py` precision/recall against fixtures (read-only).
- `dashboard-page` — scaffold a new Streamlit page.

## Do NOT delegate
- Anything touching secrets, OAuth flows, or `config.yaml` writes — hand back to user.
- Commits and pushes — surface diff, let the user run `git commit`. Two sanctioned exceptions: the `/ship` skill (commit only) and the `/data-branch-bootstrap` skill (one-shot push of the orphan `data` branch). Both gated by env-var handshakes the `pre-bash.sh` hook checks (`STARTUP_RADAR_SHIP=1` and `STARTUP_RADAR_DATA_BOOTSTRAP=1`).
