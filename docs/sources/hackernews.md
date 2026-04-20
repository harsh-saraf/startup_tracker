# Hacker News source

Key: `hackernews`. No auth.

`startup_radar/sources/hackernews.py` queries the Algolia-backed HN search API for stories matching the user's topics + funding keywords.

## Fetch flow

1. Build a query from `cfg.sources.hackernews.queries`.
2. `get_client(cfg).get("https://hn.algolia.com/api/v1/search", params=...)` wrapped in `_retry.retry(...)`.
3. Each hit with a funding regex match becomes a `Startup` record. The HN permalink is stored as the source URL.

## Config

```yaml
sources:
  hackernews:
    enabled: true
    queries:
      - "series seed"
      - "raises funding"
    hours_back: 48
```

## Gotchas

- Algolia has no auth, but it does rate-limit aggressively — the retry helper's backoff handles transient 429s.
- The simplest source in the repo; use it as the template when adding a new one (see [Adding a source](adding-a-source.md)).
