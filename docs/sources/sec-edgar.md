# SEC EDGAR source

Key: `sec_edgar`. No auth, but strict UA and rate-limit requirements.

`startup_radar/sources/sec_edgar.py` reads Form D filings (Rule 506 private offerings) to catch funding events the blogosphere misses.

## Compliance requirements

EDGAR's fair-access policy requires every request to carry:

- A descriptive `User-Agent: <Name> <email>` header.
- A request rate of **≤ 10 req/s**.

The source sets a per-request `User-Agent` override (from `cfg.sources.sec_edgar.user_agent`) on top of the shared `httpx.Client`'s default `startup-radar/<version>`. The shared client's timeout applies (`cfg.network.timeout_seconds`).

vcrpy scrubs `User-Agent` to `startup-radar-test` when recording cassettes (`tests/conftest.py::vcr_config`) — don't commit a real email in the cassette yaml.

## Fetch flow

1. GET the daily index (e.g. `/Archives/edgar/full-index/.../form.idx`).
2. Filter to Form D rows.
3. For each filing, GET the primary-doc JSON and extract issuer name, offering amount, filed date.
4. Normalize → `Startup` records.

Retries: three attempts via `_retry.retry(...)`.

## Config

```yaml
sources:
  sec_edgar:
    enabled: true
    user_agent: "Your Name your.email@example.com"
    max_filings_per_day: 500
```

## Gotchas

- Omitting the UA → EDGAR returns 403.
- Burst > 10 req/s → EDGAR briefly blocks the IP; the retry helper backs off enough that this shouldn't trigger in normal use.
- The index format occasionally changes around holidays; watch for `source.sec_edgar.streak` warnings in `doctor`.
