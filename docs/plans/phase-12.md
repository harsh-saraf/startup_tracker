# Phase 12 Execution Plan — pydantic-settings + `.env` secrets loader

> Close the residual "Phase 13" bullet called out in `docs/PRODUCTION_REFACTOR_PLAN.md` §3.3 and §5.1: introduce `Secrets(BaseSettings)` in `startup_radar/config/secrets.py`, retire the two surviving `os.getenv` sites in `startup_radar/cli.py` and `startup_radar/web/app.py`, and commit `.env.example`. Prepares the ground for Sentry (future phase) — `SENTRY_DSN` becomes the first real tenant but is NOT wired to the SDK here. **Explicitly NOT** Sentry integration, **NOT** any new env-var consumers beyond what already exists, **NOT** a rewrite of the shell-level env vars (`STARTUP_RADAR_SHIP`, `STARTUP_RADAR_DATA_BOOTSTRAP`) that live in `.claude/hooks/pre-bash.sh` — those are shell-layer and never cross into Python.

## Phase summary

- **One secrets surface: `startup_radar/config/secrets.py`.** Exposes a pydantic-settings `Secrets(BaseSettings)` class, a module-level `secrets()` accessor (lru-cached so repeated imports return the same instance), and nothing else. Matches the "one entry point" pattern already used by `config/loader.py::load_config()`.
- **Why pydantic-settings over `python-dotenv` + manual `os.getenv`.** (1) Matches the validated-config style of `AppConfig` so devs touch one library. (2) Typed fields with defaults: `log_json: bool = False`, `ci: bool = False`, `sentry_dsn: str | None = None`. (3) `extra="ignore"` by default — no `extra="forbid"` because `.env` legitimately contains shell-level vars like `STARTUP_RADAR_SHIP=1` that we do NOT want Python to trip over. (4) Single `.env` file loader honoured automatically (`env_file=".env"`).
- **Naming convention: `STARTUP_RADAR_*` prefix.** `Secrets` sets `env_prefix="STARTUP_RADAR_"` so the field `log_json` reads from `STARTUP_RADAR_LOG_JSON`. One exception: `CI` is standard across every CI system, so the `ci` field uses `validation_alias=AliasChoices("CI", "STARTUP_RADAR_CI")`. One exception: Sentry's ecosystem convention is plain `SENTRY_DSN`, so `sentry_dsn` uses `validation_alias="SENTRY_DSN"` (no prefix). Both exceptions documented inline.
- **Migration, not expansion.** Today only two Python sites read env vars (`cli.py:28`, `web/app.py:22`) and both read `STARTUP_RADAR_LOG_JSON` / `CI`. Those sites become `from startup_radar.config.secrets import secrets; configure_logging(json=secrets().log_json or secrets().ci)`. No new consumers. `SENTRY_DSN` is defined on the model but no code reads it yet — it's the placeholder for Phase 13.
- **`.env.example` committed.** Lists every field `Secrets` knows about with example values and a one-line comment each. `.env` itself stays gitignored (it already is — grepped `.gitignore`).
- **`pydantic-settings` added via `uv add`.** Not `pip install` — `pyproject.toml` + `uv.lock` stay the source of truth (CLAUDE.md invariant). No `requirements.txt`.
- **Hook already permits this.** `.claude/hooks/pre-commit-check.sh:43` grep for `os.getenv` allows `startup_radar/config/`. No hook edit. The CLAUDE.md invariant ("Never: `os.getenv()` outside `startup_radar/config/`") is already written to accommodate this — this phase makes the invariant fully true rather than aspirational (today the two CLI/web sites violate it).
- **Streamlit implication.** `@st.cache_resource` is already used for the `Storage` singleton. `secrets()` is lru-cached at module level so Streamlit's per-rerun imports see the same instance; no `@st.cache_resource` decoration needed because pydantic-settings construction is cheap and the singleton is process-global.
- **Test-seam friendly.** `secrets.cache_clear()` exposed so `tests/conftest.py` can reset between tests. `monkeypatch.setenv("STARTUP_RADAR_LOG_JSON", "1"); secrets.cache_clear()` is the pattern; documented in the module docstring.
- **No backwards-compat hacks.** The two call-site migrations are in the same commit as the `Secrets` class. No transitional `os.getenv` fallback left behind — the invariant is clean after this phase lands.

## File changes

| File | Action | Detail |
|---|---|---|
| `startup_radar/config/secrets.py` | **new** | `class Secrets(BaseSettings)` with `env_prefix="STARTUP_RADAR_"`, `env_file=".env"`, `extra="ignore"`. Fields: `log_json: bool = False`, `ci: bool = False` (alias `CI`), `sentry_dsn: str \| None = None` (alias `SENTRY_DSN`). Module-level `@lru_cache def secrets() -> Secrets`. Module docstring documents the test-seam pattern. |
| `startup_radar/config/__init__.py` | edit | Re-export `secrets` alongside existing `AppConfig`, `load_config`. Keep exports minimal. |
| `startup_radar/cli.py` | edit | Line 28 (`_want_json_logs`) becomes `from startup_radar.config import secrets; return secrets().log_json or secrets().ci`. Drop the `import os` if no other use remains (grep first). |
| `startup_radar/web/app.py` | edit | Line 22 becomes `configure_logging(json=secrets().log_json)` — no `or ci` here, matching the phase-11 plan's "explicit env-var only" call-out for the dashboard. Drop `import os` if no other use. |
| `.env.example` | **new** | Three lines: `# STARTUP_RADAR_LOG_JSON=1` (emit JSON logs), `# CI=1` (CI mode — auto-set by GH Actions), `# SENTRY_DSN=https://...@sentry.io/...` (deferred; Phase 13 tenant). All commented out by default. |
| `pyproject.toml` | edit via `uv add` | `uv add pydantic-settings` — lands in `[project.dependencies]`. `uv.lock` auto-updates. |
| `tests/unit/test_secrets.py` | **new** | Five cases: (1) unset env → all defaults. (2) `STARTUP_RADAR_LOG_JSON=1` → `log_json is True`. (3) `CI=1` → `ci is True` (alias works). (4) `SENTRY_DSN=...` → value round-trips (alias works, no prefix). (5) Unknown `STARTUP_RADAR_FOO=bar` → silently ignored (`extra="ignore"`). Each case uses `monkeypatch.setenv` + `secrets.cache_clear()`. |
| `tests/conftest.py` | edit | Autouse fixture: `secrets.cache_clear()` after each test, so env-var leaks between tests can't happen. Two-line addition next to the existing structlog autouse. |
| `.claude/CLAUDE.md` | edit | Invariants block: "Never `os.getenv()` outside `startup_radar/config/`" — drop the "(Phase 13 adds `secrets.py` …)" parenthetical since it's landed. Gotchas: add one bullet "secrets / env vars go through `startup_radar.config.secrets.secrets()` — a cached `Secrets(BaseSettings)` instance. Call `secrets.cache_clear()` in tests after `monkeypatch.setenv`. `.env` is gitignored; `.env.example` documents the knobs." |
| `docs/PRODUCTION_REFACTOR_PLAN.md` | edit | Row 14 (Dockerfile) stays. §3.3 — delete the "Still open (Phase 13)" paragraph, replace with "✅ DONE Phase 12 — `startup_radar/config/secrets.py` exposes `Secrets(BaseSettings)` + cached `secrets()`; `.env.example` committed; `SENTRY_DSN` defined but unused pending the Sentry phase." §5.1 — same swap. Add row 14a (or promote existing row) to reflect Phase 12 landed. |

## Out of scope

- Sentry SDK initialization — `SENTRY_DSN` is defined on `Secrets` so the wiring can be a one-liner later, but `sentry-sdk` is not added, `sentry_sdk.init()` is not called. That's the next phase's first task.
- Rewriting `tests/conftest.py:49` which reads `os.environ.get("CI")` — `tests/` is exempt from the invariant (CLAUDE.md line 62 scopes the rule to `startup_radar/`), and vcrpy's fixture setup legitimately needs the raw env check at collection time before any app code runs.
- `STARTUP_RADAR_DB_URL` — explicitly rejected in `PRODUCTION_REFACTOR_PLAN.md` §3.5 ("`cfg.output.sqlite.path` covers the single knob this tool needs"). Not a field on `Secrets`.
- `STARTUP_RADAR_SHIP` / `STARTUP_RADAR_DATA_BOOTSTRAP` — shell-only, consumed by `.claude/hooks/pre-bash.sh`. Adding them to `Secrets` would imply Python reads them, which it doesn't. Leave alone.
- Dashboard UI changes. No new env-var surface in the UI, no "Secrets loaded: ..." diagnostic panel.

## Tests

Six new / touched test points:

1. `tests/unit/test_secrets.py` — the five cases listed above.
2. `tests/conftest.py` — autouse `secrets.cache_clear()` fixture, verified by running `test_secrets.py` twice in the same session (no leak).
3. `tests/unit/test_cli_status.py` (existing) — confirm nothing regressed; the file already monkeypatches env, it should still pass because the cache-clear fixture handles teardown.
4. `tests/unit/test_web_smoke.py` (existing) — AppTest shell still boots; confirms the `configure_logging(json=secrets().log_json)` change didn't break dashboard import order.
5. `make ci` — ruff + mypy + full pytest all green. Mypy may need a `py.typed` marker if pydantic-settings ships without one (it does — v2.x has `py.typed`). No action expected.
6. Manual: `cp .env.example .env && echo 'STARTUP_RADAR_LOG_JSON=1' >> .env && uv run startup-radar status` — confirms `.env` loading works end-to-end (structlog renders JSON).

## Exit criteria

- [ ] `startup_radar/config/secrets.py` exists with `Secrets(BaseSettings)` + cached `secrets()` accessor.
- [ ] `startup_radar/cli.py` and `startup_radar/web/app.py` contain zero `os.getenv` / `os.environ` references.
- [ ] `grep -rn "os\.getenv\|os\.environ" startup_radar/ | grep -v config/` returns zero matches.
- [ ] `.env.example` committed at repo root.
- [ ] `pydantic-settings` listed in `pyproject.toml` `[project.dependencies]`; `uv.lock` regenerated.
- [ ] `tests/unit/test_secrets.py` passes all five cases.
- [ ] `make ci` green on `refactor/v2`.
- [ ] `.claude/CLAUDE.md` invariants + gotchas updated; "(Phase 13 adds `secrets.py` …)" parenthetical removed.
- [ ] `docs/PRODUCTION_REFACTOR_PLAN.md` §3.3 + §5.1 reflect Phase 12 landed; row added to the tracker table.
- [ ] Commit message follows conventional-commits: `feat(config): pydantic-settings Secrets + .env.example (Phase 12)`. Tag `phase-12` after merge.

## Rollback

Revert the single commit. `.env.example` removal and dependency drop are covered by the revert; the only persistent artifact would be a developer-local `.env` file (never committed, gitignored) which stays harmless because no code reads it post-revert.
