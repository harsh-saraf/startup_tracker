# Reasoning trail

Load-bearing context for *why* the refactor is shaped the way it is. These documents are not onboarding material — they're the decision log.

- **[Refactor plan](../PRODUCTION_REFACTOR_PLAN.md)** — 18-phase execution table with status and per-phase summaries. The source of truth for "what shipped" vs "what's next".
- **[Critique appendix](../CRITIQUE_APPENDIX.md)** — section-by-section record of rejected patterns (no alembic, no Postgres, no async, no Sentry, no `web/components/` directory until ≥3 reuses, etc.) with rationale. Cited heavily from CLAUDE.md invariants.
- **[Audit findings](../AUDIT_FINDINGS.md)** — pre-refactor inventory of smells and latent bugs with resolution status per phase.
- **[Phases](phases.md)** — one-line summary of every `docs/plans/phase-N.md` plan document.

## How to use these

If you're about to propose a pattern the refactor plan deliberately rejected, a grep through the critique appendix will usually surface the reasoning behind the rejection. If it doesn't, the pattern is genuinely up for debate — open a PR or a phase-plan document.
