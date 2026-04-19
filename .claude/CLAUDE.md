# Startup Radar — Claude Context

Single-user Python tool that aggregates startup-funding signals from RSS, Hacker News, SEC EDGAR, and (optional) Gmail newsletters; filters by user criteria; serves a Streamlit dashboard with application tracking, warm-intro lookup, and AI-generated research briefs.

## Stack
- Python ≥3.10 (`pyproject.toml`); eventual target 3.11.
- Package manager: `pip` today; `uv` migration in Phase 4 (lockfile becomes source of truth).
- DB: SQLite, single file (`startup_radar.db`).
- Web: Streamlit (single-file `app.py`, ~1100 LOC; multi-page split in Phase 11).
- HTTP: `requests` today; migrating to `httpx` in Phase 13.
- Parsing: `feedparser`, `beautifulsoup4`.
- Configuration: `config.yaml` validated by `config_loader.py`; pydantic schema lands Phase 7.
- Secrets: `credentials.json`, `token.json`, `.env` — never commit, never read via shell.

## Repo layout
```
.
├── main.py              # pipeline entry — extends to Typer CLI in Phase 6
├── daily_run.py         # cron wrapper with logging + 15-min timeout
├── app.py               # Streamlit dashboard (5 pages, single file)
├── deepdive.py          # AI research brief generator
├── database.py          # SQLite layer (33 functions, raw sqlite3)
├── filters.py           # StartupFilter + JobFilter classes
├── models.py            # @dataclass Startup, JobMatch
├── config_loader.py     # YAML config loader (4-key validation)
├── connections.py       # LinkedIn CSV → tier-1/tier-2 intro lookup
├── sources/{rss,hackernews,sec_edgar,gmail}.py
├── sinks/google_sheets.py
├── scheduling/          # cron, launchd, Windows Task templates
├── tests/test_smoke.py  # Phase 0 placeholder; real coverage Phase 10
├── docs/                # PRODUCTION_REFACTOR_PLAN, CRITIQUE_APPENDIX, AUDIT_FINDINGS, plans/phase-N
└── .claude/             # this directory — harness
```
Target layout (Phase 5+) lives in `docs/PRODUCTION_REFACTOR_PLAN.md` §3.1.

## Core invariants
- **Must:** every new HTTP call uses `timeout=` (or shared `httpx.Client` once it lands). `feedparser` is the exception — see `sources/rss.py:18`.
- **Must:** every source returns `list[Startup]`.
- **Must:** company-name normalization goes through `_normalize_company` in `main.py:22`.
- **Never:** `print()` outside `main.py`, `daily_run.py`, `deepdive.py`, or `tests/` — use a logger.
- **Never:** `os.getenv()` outside `config_loader.py` (later: `startup_radar/config/`).
- **Never:** edit `credentials.json`, `token.json`, `.env`, `uv.lock`, or `*.db` files.
- **Never:** edit `requirements.txt` once Phase 4 migration completes.
- **Never:** add Postgres, alembic, async pipeline, or dashboard auth — out of scope per `docs/CRITIQUE_APPENDIX.md` §12.

## Common commands
```bash
make lint           # ruff check
make format         # ruff format (writes)
make format-check   # ruff format --check (no writes)
make test           # pytest
make typecheck      # mypy
make ci             # lint + format-check + typecheck + test
make serve          # streamlit run app.py
make run            # python main.py
```

## Gotchas
- `feedparser` does NOT take a `timeout` kwarg — `sources/rss.py:18` uses `socket.setdefaulttimeout(20)` at module load.
- SEC EDGAR requires `User-Agent: Name email@example.com` header AND ≤10 req/s.
- Streamlit re-runs the entire script on every interaction — wrap DB reads in `@st.cache_data(ttl=60)` (already done at `app.py:59`).
- GH Actions cache for the SQLite DB is unsound (`docs/CRITIQUE_APPENDIX.md` §1, item 1) — Phase 9 replaces it with commit-to-data-branch.
- OAuth scopes for Gmail (`gmail.readonly`) and Sheets (`spreadsheets`) are merged into a single `token.json` — Phase 0 fix.
- Dedup key strips legal suffixes (`inc`, `llc`, `corp`, `gmbh`, `labs`, etc.) — see `_LEGAL_SUFFIX_RE` in `main.py:16`. Real failure mode is "OpenAI" vs "Open AI Inc.", not whitespace.

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
- `source-implementer` — scaffold a new data source under `sources/`.
- `filter-tuner` — diagnose `filters.py` precision/recall against fixtures (read-only).
- `dashboard-page` — scaffold a new Streamlit page.

## Do NOT delegate
- Anything touching secrets, OAuth flows, or `config.yaml` writes — hand back to user.
- Commits and pushes — surface diff, let the user run `git commit`.
