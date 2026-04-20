# Phases

Every phase of the production refactor lands with a plan doc at `docs/plans/phase-N.md` and a git tag `phase-N`. One-line summary of each:

- **[Phase 1](../plans/phase-1.md)** — Claude Code harness (`.claude/` directory, rules, skills, subagents).
- **[Phase 2](../plans/phase-2.md)** — `uv` + `pyproject.toml` migration; retire `requirements.txt`.
- **[Phase 3](../plans/phase-3.md)** — `startup_radar/` package extraction; `Source` ABC.
- **[Phase 4](../plans/phase-4.md)** — Typer CLI; `startup-radar run / serve / deepdive`.
- **[Phase 5](../plans/phase-5.md)** — pydantic `AppConfig`; `filters.py` + `parsing/` hoisted into the package.
- **[Phase 6](../plans/phase-6.md)** — resilience CLI (`backup`, `doctor`, `status`) + tests.
- **[Phase 7](../plans/phase-7.md)** — GH Actions DB persistence via the orphan `data` branch.
- **[Phase 7.5](../plans/phase-7.5.md)** — `/data-branch-bootstrap` + `/data-branch-restore` skills + pre-bash env-var handshakes.
- **[Phase 8](../plans/phase-8.md)** — vcrpy cassette-backed integration tests per source.
- **[Phase 9](../plans/phase-9.md)** — Streamlit multi-page split (`web/app.py` shell + `web/pages/*`).
- **[Phase 10](../plans/phase-10.md)** — `SqliteStorage` class + `PRAGMA user_version` migrator.
- **[Phase 11](../plans/phase-11.md)** — structlog pipeline + retry helper + `runs` table.
- **[Phase 12](../plans/phase-12.md)** — `pydantic-settings` secrets loader + `.env`.
- **[Phase 13](../plans/phase-13.md)** — shared `httpx.Client`; retire `requests`.
- **[Phase 14](../plans/phase-14.md)** — Dockerfile (multi-stage slim image) + top-level `--config` flag.
- **[Phase 15](../plans/phase-15.md)** — MkDocs Material docs site + GH Pages publish.
- **[Phase 16](../plans/phase-16.md)** — `StartupRadarError` taxonomy + CLI error boundary + `--debug` flag.
