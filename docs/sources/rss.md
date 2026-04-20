# RSS source

Key: `rss`. No auth.

`startup_radar/sources/rss.py` pulls a user-configurable list of funding-adjacent feeds (TechCrunch, StrictlyVC, Term Sheet, etc.) and extracts candidates via the funding regexes in `startup_radar/parsing/funding.py`.

## Fetch flow

1. `get_client(cfg).get(url)` — bytes in via the shared `httpx.Client` (Phase 13).
2. `feedparser.parse(r.content)` — parsing only; `feedparser` does **not** make its own HTTP calls.
3. Per entry: title + summary → `AMOUNT_RE` / `STAGE_RE` / `COMPANY_SUBJECT_RE` / `COMPANY_INLINE_RE` → `Startup(...)`.

Phase 13 retired the old `socket.setdefaulttimeout(20)` module-load hack — timeout is inherited from the shared client (`cfg.network.timeout_seconds`, default 10 s).

## Config

```yaml
sources:
  rss:
    enabled: true
    feeds:
      - https://techcrunch.com/category/venture/feed/
      - https://www.strictlyvc.com/feed/
```

## Gotchas

- Some feeds 301-redirect — the shared client follows them (`follow_redirects=True`).
- Malformed feeds surface in `parsed.bozo`; the source logs a warning at `source.fetch_failed` and returns `[]` for that feed (other feeds in the list still run).
- Retries: three attempts via `_retry.retry(...)` with `(1, 2, 4)` s backoff.
