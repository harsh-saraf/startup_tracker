# Adding a source

This walkthrough adds a new data source end-to-end. The simplest live source is `startup_radar/sources/hackernews.py` — ~100 LOC, no OAuth, single HTTP call — use it as the reference.

## 1. Subclass `Source`

Create `startup_radar/sources/<name>.py`:

```python
from __future__ import annotations

from startup_radar.http import get_client
from startup_radar.models import Startup
from startup_radar.observability.logging import get_logger
from startup_radar.sources._retry import retry
from startup_radar.sources.base import Source

log = get_logger(__name__)


class YourSource(Source):
    name = "Your Source"
    enabled_key = "yoursource"  # must match the key in config.yaml's `sources:` block

    def fetch(self, cfg, storage=None) -> list[Startup]:
        client = get_client(cfg)
        try:
            r = retry(
                lambda: client.get("https://example.com/feed.json"),
                on=(OSError,),
                context={"source": self.name},
            )
            r.raise_for_status()
        except Exception as e:
            log.warning("source.fetch_failed", source=self.name, error=str(e))
            return []
        # … parse r.json() into Startup records …
        return []

    def healthcheck(self, cfg, *, network: bool) -> tuple[bool, str]:
        if not network:
            return True, "config-only check passed"
        # fast HEAD or cheap GET for reachability
        return True, "reachable"
```

Invariants enforced by [`.claude/rules/sources.md`](https://github.com/xavierahojjx-afk/startup-radar-template/blob/main/.claude/rules/sources.md):

- Outbound HTTP **must** go through `get_client(cfg)`.
- Network calls **must** be wrapped in `_retry.retry(...)`.
- Funding regexes live **only** in `startup_radar/parsing/funding.py` — never duplicate them in a source.
- Company-name normalization goes through `normalize_company` / `dedup_key` in `startup_radar/parsing/normalize.py`.
- No `print()` — use `get_logger(__name__)` and structured kwargs.

## 2. Register

Add an entry to `startup_radar/sources/registry.py`:

```python
from startup_radar.sources.yoursource import YourSource

SOURCES: dict[str, Source] = {
    "rss": RssSource(),
    "hackernews": HackerNewsSource(),
    "sec_edgar": SecEdgarSource(),
    "gmail": GmailSource(),
    "yoursource": YourSource(),  # ← new
}
```

## 3. Config schema

Add a `YourSourceConfig` model to `startup_radar/config/schema.py` with an `enabled: bool` field and any knobs you need. Reference it from `SourcesConfig`. Update `config.example.yaml` with a commented-out default block so users know how to enable it.

## 4. Test

Write two cassette-backed tests under `tests/integration/test_<name>.py` — happy-path and empty-response — per [`.claude/rules/testing.md`](https://github.com/xavierahojjx-afk/startup-radar-template/blob/main/.claude/rules/testing.md).

Record the first cassette locally:

```bash
uv run pytest tests/integration/test_<name>.py
```

vcrpy defaults to `record_mode=once` locally, so the first run hits the network and writes `tests/fixtures/cassettes/<name>/*.yaml`. Subsequent runs replay.

`CI=1` flips `record_mode` to `none` — a missing cassette fails the test loudly rather than sneaking a live request into CI.

Re-record by deleting the yaml and running the test again. EDGAR cassettes scrub `User-Agent` to `startup-radar-test`; don't commit a real email.

## 5. Healthcheck

`doctor --network` walks the registry, so your `healthcheck(cfg, network=...)` method is picked up automatically. Return `(ok: bool, detail: str)`. Keep the non-network path fast and truthful — a bad credential is an `ok=False` even without `--network`.

## 6. Subagent: `source-implementer`

Claude Code ships a `source-implementer` subagent that scaffolds steps 1–3 (Source subclass + registry entry + cassette skeleton). Hand it the source name and a sample URL; it writes the files and hands back a test plan for you to record cassettes against.

## 7. Run the pipeline

```bash
uv run startup-radar doctor --network
uv run startup-radar run
uv run startup-radar status    # see Per-source health: block
```

A source that fails three runs in a row shows up as `⚠ source.<key>.streak` in `doctor` — advisory only, it doesn't increment the failure count (Phase 11).
