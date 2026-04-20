# Critique Appendix — Senior Engineer Audit of the Refactor Plan

> Independent review of `PRODUCTION_REFACTOR_PLAN.md` and `AUDIT_FINDINGS.md`. Calibrates the plan against "single-user personal tool that wants production-grade DX" rather than a startup SaaS.

## 1. Diagnosis accuracy

Mostly correct. Verified line numbers against HEAD:

- **GH Actions cache (Tier 0 #1):** Confirmed `.github/workflows/daily.yml:24-29`. Diagnosis "DB never persists" is **slightly overstated** — `restore-keys: startup-radar-db-` matches the most recent prefix-keyed entry, so persistence usually works. Real bugs are: (a) writes are non-deterministic under concurrent runs, (b) GH evicts caches after 7 days no-access, (c) caches are scoped to branch with fallback — PR runs can poison main's data. Tighten wording: not "broken," it's "unsound."
- **OAuth scope split (Tier 0 #2):** Confirmed. Real bug.
- **Silent failures (Tier 0 #3):** Confirmed. Real.
- **Naive dedup (Tier 0 #4):** Confirmed at `main.py:21`. The plan's example is wrong — `re.sub(r"[\s.\-]+", "")` *does* collapse "We Work" → "wework". Real failure mode is **"OpenAI" vs "Open AI Inc."** Fix the example.
- **Streamlit caching (Tier 0 #5):** Confirmed. Biggest win/effort ratio.
- **HTTP timeouts (Tier 0 #6):** `feedparser` doesn't take a timeout kwarg — needs `socket.setdefaulttimeout()` or switch to `httpx`. Plan glosses over.
- **DB connection-per-call:** Confirmed. For single-user SQLite on local disk this is **a non-issue performance-wise** — SQLite open is microseconds. Push back on framing as "wasteful." Real reason to refactor is testability + transactional grouping.

## 2. CLI surface

Shape is right. Adjustments:
- Drop `db` as a top-level verb — collides cognitively with the source-of-truth name. Use `startup-radar admin <op>`.
- Add `startup-radar logs --tail` and `startup-radar status` (last run age, source health). Otherwise users `tail -f logs/*.log` anyway.
- Make sure `schedule install` actually replaces `scheduling/*` rather than living alongside.

## 3. `uv` vs Poetry vs pip

`uv` is correct in 2026. Gotchas:
- Don't commit `uv.lock` AND `requirements.txt` — pick one, generate the other via `uv export`.
- `pipx install startup-radar` implies PyPI publication. **For a single-user personal tool, don't publish.** `pipx install git+https://github.com/...` works and skips a release pipeline you don't need.

## 4. SQLite + Alembic + Postgres

- **Alembic is overkill.** A 50-line homegrown migrator using `PRAGMA user_version` + numbered `.sql` files is sufficient. Mention alembic as "if this ever goes multi-tenant."
- **Postgres is cargo-cult here.** Drop from §3.5 and docker-compose. Single-user, no team. If durable cloud DB needed, **Turso (libSQL)** keeps SQLite semantics with a free remote endpoint — but only add if the dashboard needs to read remote DB (it doesn't).

## 5. GH Actions DB persistence

Best answer: **commit-to-data-branch** via `EndBug/add-and-commit` to an orphan `data` branch, with nightly artifact upload as backup. Reasons:
- Free, observable (`git log data -- startup_radar.db`), recoverable.
- No new infra, no API keys.
- Footgun: SQLite binary diffs bloat the branch — mitigate by force-pushing `data` weekly.

Plan should pick **one** option, not offer three.

## 6. Async pipeline

**Premature.** Four sources, ~1 minute total, daily. `asyncio.gather` saves ~45s/day for one user. Complexity cost outweighs benefit. Use `ThreadPoolExecutor(max_workers=4)` (5 lines, sync everywhere else still works) or skip. **Demote to Tier 4.**

## 7. Streamlit decomposition

Reasonable, but:
- **Skip `components/` until ≥3 reuses.** Premature DRY in Streamlit creates rerun-state bugs nastier than copy-paste.
- The `@st.cache_data` win is correctness; the rest is taste.
- Streamlit native multi-page has known gotchas with shared session state — call out so future-Claude doesn't get bitten.

## 8. Claude harness

Two real problems:
- **`Stop` hook running `make ci`** will be hated within a week. ruff+mypy+pytest is 30-60s; running on every Stop event when you asked for a one-line clarification is friction. Fix: lint+format only on `Stop`; full CI behind a `/ship` skill. Or scope `Stop` matcher to fire only when files were edited.
- **`post-edit.sh` async** means Claude moves on before format completes — can race next edit. Make sync but only on changed file.
- Add `Edit(uv.lock)` deny (regenerate via `uv lock`, not manual edit).
- Drop `migration-author` subagent (no alembic).
- Defer `playwright` MCP until multi-page Streamlit work warrants it. `context7` is genuinely useful.

## 9. Effort estimates

**Underestimated by ~40%:**
- CI + vcrpy fixtures: 3-4 days, not 2 (cassette recording, auth-bearing requests, time-varying matchers).
- `app.py` decomposition: 2 days minimum (Streamlit session-state migration is fiddly).
- Storage + migrations: 1 day if homegrown migrator; 2-3 if alembic.

Realistic total: **15-18 days** for careful single-developer pass.

## 10. Execution order

- **Typer CLI (item 2) should come after Source ABC (item 4)** — otherwise you rewrite the CLI's source-orchestration code.
- **CI scaffolding (item 6) should come right after item 1** — every subsequent refactor without tests is risky. Half-day if you defer fixtures.
- **`.claude/` harness (item 7) at slot 7 is too late.** Move to slot 3 — the harness is what lets you safely do 8-12.

## 11. Missing items

Significant gaps:
- **`startup-radar backup`** → tarball of DB + config + token. Single most important resilience feature for a personal tool. Trivial.
- **`startup-radar export --format csv|json`** — user owns their data.
- **`PRAGMA user_version`** schema versioning (even without alembic).
- **`threading.Timer` race in `daily_run.py:70`** — low probability but real.
- **Gmail token auto-refresh on expiry** — `daily_run.py:88-90` only *detects* and tells user to re-auth manually. Personal unattended cron should automate.
- **`setuptools-scm` git-tag versioning** — move from Tier 4 to Tier 1.
- **`mypy --strict` posture** — commit or explicitly defer.
- **Robots.txt / ToS posture for sources** — one-liner.
- **Telemetry: explicitly NONE.** State this so future-you doesn't ask in 6 months.

Skip: GDPR (no third-party PII), error reporting (Sentry covered), type stubs (`mypy --install-types`), semver (unpublished tool), CHANGELOG (skip for personal tool).

## 12. Personal-vs-production calibration

Plan is calibrated for a small startup, not personal tool. **Drop or demote:**

| Plan item | Verdict | Reason |
|---|---|---|
| Postgres in compose | Drop | No second user. |
| Alembic | Drop | Homegrown user_version migrator suffices. |
| SQLAlchemy Core | Drop | 33 functions of straightforward SQL; abstraction tax > benefit. |
| Circuit breaker | Demote | Per-source failure flag is enough. |
| asyncio | Demote | See §6. |
| Dashboard auth | Drop | localhost-only. Add only if deployed remotely. |
| PyPI release pipeline | Drop | `pipx install git+...` is fine. |
| migration-author subagent | Drop | No alembic. |
| playwright MCP | Defer | Until multi-page dashboard work. |
| Docker compose `dev` | Demote | `uv run startup-radar serve` IS the dev workflow. |

**Keep firmly** (earn keep at any scale):
Typer CLI, pydantic config, `uv` + lockfile, structlog, tests + vcrpy, Streamlit caching, GH Actions DB persistence fix, Source ABC + parsing dedup, `.claude/` harness with sane hooks, `doctor` command, **backup/restore** (add).

Line: **anything that prevents data loss, prevents foot-shooting, or makes one-command DX possible** is worth the effort. Anything that adds a second deployment target, second user, or second persistence engine is not.

---

**Bottom line:** plan is directionally excellent. Cut Postgres, alembic, async, dashboard auth, PyPI release, `Stop`-hook `make ci`. Add backup/restore, data export, `PRAGMA user_version`. Re-order so CI scaffolding and Claude harness come before big refactors. Bump estimate from 10-13 days to **15-18**.
