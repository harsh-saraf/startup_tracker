---
name: source-implementer
description: Use when adding a new data source to the Startup Radar pipeline. Scaffolds the source module, wiring, and a vcrpy fixture skeleton.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# source-implementer

## When to use
- User says "add an X source" or "fetch from Y feed".
- A new data source needs scaffolding: module, registration, parsing, tests.

## Process
1. Read `.claude/rules/sources.md` and `models.py` to understand the `Startup` shape.
2. Read `sources/rss.py` as the cleanest reference pattern.
3. Create `sources/<name>.py` exposing `def fetch(cfg: dict) -> list[Startup]`.
4. Wire into `main.py` (until the registry/ABC lands in Phase 5; then add to `sources/registry.py`).
5. Add a vcrpy cassette skeleton under `tests/fixtures/cassettes/<name>/` and a `tests/unit/test_<name>.py` with one happy path + one empty-response test.
6. Surface to user: file diff, what config keys to add, what to verify with `make run`.

## Constraints
- Never invent feed URLs — get them from the user.
- Always set HTTP timeout (or `socket.setdefaulttimeout()` for `feedparser`).
- Never `print()` — use the existing logger pattern.
- Never edit `requirements.txt` or `uv.lock`; if a new dep is needed, surface it for the user to add.
