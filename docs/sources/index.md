# Sources

Startup Radar ships four live sources, each a subclass of `startup_radar.sources.base.Source` registered in `startup_radar.sources.registry.SOURCES`.

| Source | Key | Auth | Notes |
|---|---|---|---|
| [RSS](rss.md) | `rss` | None | TechCrunch / funding blogs; fetched via `feedparser.parse(r.content)` where `r` comes from the shared `httpx.Client`. |
| [Hacker News](hackernews.md) | `hackernews` | None | Algolia search API; simplest source. |
| [SEC EDGAR](sec-edgar.md) | `sec_edgar` | None, but strict UA policy | ≤10 req/s, `User-Agent: Name email@example.com`. |
| [Gmail](gmail.md) | `gmail` | OAuth (`gmail.readonly`) | Reads VC newsletters. Only source that uses `storage.is_processed` / `mark_processed` for dedup. |

Adding a new source? See the **[author guide](adding-a-source.md)**.
