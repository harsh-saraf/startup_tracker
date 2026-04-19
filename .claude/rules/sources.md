---
paths:
  - "sources/**"
  - "startup_radar/sources/**"
---

# Source-author rules

- **Must:** every source exposes `def fetch(...) -> list[Startup]` (until the Source ABC lands in Phase 5).
- **Must:** every HTTP call passes `timeout=` (or uses the shared client). `feedparser` is an exception — set `socket.setdefaulttimeout()` at module load (see `sources/rss.py:18`).
- **Must:** SEC EDGAR requests include `User-Agent: <Name> <email>` header (see `sources/sec_edgar.py:20`).
- **Must:** parsing helpers (`_AMOUNT_RE`, `_STAGE_RE`) live in **one** module. Today they're duplicated in `rss.py:18`, `hackernews.py:16`, `sec_edgar.py`, `deepdive.py` — when extending, leave the duplication; when refactoring, extract to `parsing/funding.py` (Phase 5).
- **Never:** swallow exceptions to `print()`. Log with severity and either re-raise or return `[]` plus a counted failure.
- **Never:** hardcode feed URLs in source code. Read from `config.yaml`.
- **Never:** read `os.environ` directly inside a source. Accept config dict argument.
- **Must:** any new source ships with a vcrpy cassette under `tests/fixtures/cassettes/<name>/` and a happy-path + empty-response test (Phase 10 dependency; flag if blocked).
- **Must:** the company name produced by a source is the raw name as it appears in the wild — `_normalize_company` in `main.py:22` handles canonicalization. Don't normalize twice.
