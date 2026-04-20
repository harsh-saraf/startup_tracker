# Contributing

Startup Radar is a single-user tool with a small, rigorous refactor harness. Contributions are welcome; the conventions below keep the codebase coherent.

## Dev environment

```bash
# 1. Install the toolchain
uv sync --all-extras

# 2. Run the full local CI
make ci          # ruff check + format-check + mypy + pytest

# 3. Useful loops
make test        # pytest only
make lint        # ruff check
make format      # ruff format (writes)
make typecheck   # mypy

# 4. Docs loop (Phase 15)
uv sync --extra docs
make docs        # strict build to ./site
make docs-serve  # live-reload on :8000
```

No `requirements.txt`. `pyproject.toml` + `uv.lock` are authoritative.

## Claude Code harness

The repo ships a set of `.claude/` assets — slash-commands (skills), agents, hooks, and rules — tuned for this codebase. See `.claude/CLAUDE.md` for the full playbook. Key points:

- **Skills** — `/radar` (state-aware orchestrator: onboarding, run, serve, status, doctor, backup), `/research <Company>` (research brief .docx), `/ship` (sanctioned commit path), `/data-branch-bootstrap`, `/data-branch-restore`. The first two auto-invoke on natural-language intent; the rest are explicit.
- **Hooks** — `.claude/hooks/pre-bash.sh` blocks destructive recursive deletes and gates `git commit` + push-to-`data` behind env-var handshakes (`STARTUP_RADAR_SHIP=1` and `STARTUP_RADAR_DATA_BOOTSTRAP=1`).
- **Rules** — per-domain conventions under `.claude/rules/` (sources, storage, dashboard, observability, testing). Loaded into Claude's context when editing matching files.

## Commit conventions

- **Conventional Commits.** `feat(…)` / `fix(…)` / `refactor(…)` / `docs(…)` / `chore(…)` / `test(…)`.
- **Scope.** Prefer the subsystem (`source`, `storage`, `http`, `observability`, `config`, `web`, `cli`, `docker`).
- **Body.** Focus on *why*, not *what*. The diff shows the what.
- **Co-author.** When Claude Code drafts a commit it includes `Co-Authored-By: Claude …` — keep that.
- **`/ship` skill.** Runs `make ci`, drafts a conventional commit from the staged diff, and commits. The only sanctioned path for Claude to create a commit in this repo.

## PR flow

1. Branch off `main` (or `refactor/v2` during the production refactor).
2. Commit via `/ship` or manually; one logical change per PR.
3. Open the PR against `main`. CI (`make ci`) must be green.
4. For docs-only PRs, the `.github/workflows/docs.yml` build must also be green.

## Adding a phase plan

The production refactor is phased — each phase has a plan doc at `docs/plans/phase-N.md` and lands on a `phase-N` git tag. See `docs/PRODUCTION_REFACTOR_PLAN.md` for the execution table, and any existing plan (e.g. `docs/plans/phase-13.md`) for the voice and structure.

## Adding a source

See the [source author guide](../sources/adding-a-source.md) — concrete walkthrough of subclassing `Source`, wiring into `registry.py`, recording vcrpy cassettes, and exercising the `source-implementer` subagent.
