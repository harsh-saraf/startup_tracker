# Startup Radar — Production Docs

Reading order:

1. **[PRODUCTION_REFACTOR_PLAN.md](./PRODUCTION_REFACTOR_PLAN.md)** — the plan. §0a "Calibration overrides" supersedes anything below it that conflicts.
2. **[CRITIQUE_APPENDIX.md](./CRITIQUE_APPENDIX.md)** — independent senior-engineer audit of the plan. Reasoning behind §0a.
3. **[AUDIT_FINDINGS.md](./AUDIT_FINDINGS.md)** — the diagnosis the plan is built on. Cited line numbers in current code.

## TL;DR

- Repo today is a working prototype with three entry points, no tests, a 1,104-line dashboard, and a broken GH Actions DB persistence.
- Plan turns it into a `pipx`-installable single-CLI tool with one-command DX, real tests, and a robust `.claude/` harness.
- Calibrated for **single-user personal tool**, not SaaS — drops Postgres, alembic, async, dashboard auth, PyPI release.
- Estimate: **15-18 engineering days** for full transformation; 6 days delivers 80% of the value.

## Top 6 (do these first)
1. `@st.cache_data(ttl=60)` on `app.py:58 load_data()` — 30 min, biggest win.
2. CI scaffolding (ruff + mypy + empty pytest) — 0.5 day.
3. `.claude/` harness with sane hooks — 0.5 day.
4. `pyproject.toml` + `uv` + entry-point — 1 day.
5. Source ABC + centralized parsing — 0.5 day.
6. Typer CLI (`startup-radar run|serve|deepdive|init|doctor|backup|status`) — 1 day.
