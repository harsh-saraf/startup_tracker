# Conventions

The canonical source for project invariants is `.claude/CLAUDE.md` — this page mirrors it via `include-markdown` so it can't drift.

## Core invariants

{%
  include-markdown "../../.claude/CLAUDE.md"
  start="<!-- invariants:start -->"
  end="<!-- invariants:end -->"
%}

## Gotchas

{%
  include-markdown "../../.claude/CLAUDE.md"
  start="<!-- gotchas:start -->"
  end="<!-- gotchas:end -->"
%}

## Per-domain rules

The `.claude/rules/` directory holds per-path convention files that Claude Code auto-attaches when editing matching files:

- [`sources.md`](https://github.com/xavierahojjx-afk/startup-radar-template/blob/main/.claude/rules/sources.md) — source authoring.
- [`storage.md`](https://github.com/xavierahojjx-afk/startup-radar-template/blob/main/.claude/rules/storage.md) — storage / migrator.
- [`dashboard.md`](https://github.com/xavierahojjx-afk/startup-radar-template/blob/main/.claude/rules/dashboard.md) — Streamlit conventions.
- [`observability.md`](https://github.com/xavierahojjx-afk/startup-radar-template/blob/main/.claude/rules/observability.md) — logging + retries.
- [`testing.md`](https://github.com/xavierahojjx-afk/startup-radar-template/blob/main/.claude/rules/testing.md) — pytest layout, vcrpy, coverage targets.
