---
name: filter-tuner
description: Use to diagnose or tune `filters.py` — measures precision/recall against fixtures and proposes targeted changes.
allowed-tools: [Read, Glob, Grep, Bash]
---

# filter-tuner

## When to use
- User says "filter is too strict" / "filter is too loose" / "why was X dropped".
- Need to evaluate filter behaviour against a fixture or recent run.

## Process
1. Read `filters.py` and `config.yaml` (or `config.example.yaml`) to understand current rules.
2. Identify a fixture set: either the live DB (read-only) or `tests/fixtures/`.
3. Run a dry-run script: `python -c "from filters import StartupFilter; ..."` to compute kept/dropped counts.
4. Categorize drops: by source, by reason (stage, location, role, industry).
5. Propose a single-change diff with expected delta.

## Constraints
- Read-only — do NOT modify `filters.py` directly. Output a diff and rationale; let the user accept.
- Never load secrets or hit the network.
- Never write to the live DB.
