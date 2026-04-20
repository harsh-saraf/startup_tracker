# Phase 8 Execution Plan — vcrpy fixtures + real source tests

> Replace `tests/test_smoke.py`'s placeholder with a real integration-test layer for every source. Record each source's HTTP interaction once as a vcrpy cassette, replay it in CI, and prove the `fetch() -> list[Startup]` contract end-to-end. Lands the coverage target from `docs/PRODUCTION_REFACTOR_PLAN.md` §4.1 (sources ≥70%, pure-function modules ≥90%) and closes row 10 in §0a's re-ordered execution. Also ships the missing `.github/workflows/ci.yml` so PRs actually get gated.

## Phase summary

- **Restructure `tests/`** into `tests/unit/` and `tests/integration/` per `.claude/rules/testing.md`. Existing Phase 3/5/6 tests move under `unit/`. No test-logic changes during the move.
- **Add `tests/fixtures/cassettes/<source>/`** for the three HTTP sources (`rss`, `hackernews`, `sec_edgar`). Gmail is handled differently (§2.4) — no cassettes, `_get_service()` is stubbed via a `google.*` injection point.
- **Write integration tests per source**, two minimum per `.claude/rules/testing.md`:
  - Happy path — cassette with realistic payload → `fetch()` returns N populated `Startup`s whose fields match the payload.
  - Empty response — cassette with 0 hits / empty RSS → `fetch()` returns `[]` cleanly (no exception, no partial rows).
  - Third test for each source: a failure mode (timeout, 500, malformed JSON) → returns `[]` AND logs at `warning` via `caplog`.
- **Expand unit coverage** on `filters.py`, `parsing/funding.py`, `parsing/normalize.py`, `models.py`. These are pure and cheap — get them to 90% without cassettes.
- **Wire vcrpy globally** via a `conftest.py`-level `vcr` fixture so cassette discovery is uniform. Scrub `User-Agent`, `Authorization`, and `Cookie` headers on record. Set `record_mode = "none"` in CI (`CI=1` env), `"once"` locally.
- **Add `.github/workflows/ci.yml`** — row 2 of §0a's re-ordered execution has been carried as implicit debt since Phase 1 (no GH-side gate; `make ci` is local-only). PR workflow: `uv sync`, `make ci`, upload `coverage.xml`. One `ubuntu-latest` × one Python version (3.11). No matrix; single-user tool.
- **Coverage threshold** enforced by `pytest-cov` via `--cov-fail-under=70` on `startup_radar/`. Pure-function modules get their own stricter check via a per-module threshold in `pyproject.toml` (`[tool.coverage.report]` with `fail_under = 70` global + a report step that greps for `filters` / `parsing` having ≥90%).
- **Refactor `gmail.py`** minimally to make `_get_service()` swappable: extract to a module-level callable (or a `GmailSource.service_factory` class attribute) so tests inject a `MagicMock` that returns canned Gmail API responses. No behavior change; no new config key.
- **Docs**: `README.md` "Development" section gains a "Running tests / re-recording cassettes" subsection; `docs/plans/phase-8.md` is this doc; `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 10 → ✅; `.claude/CLAUDE.md` "Common commands" gets `make test` already present, no change needed, but "Gotchas" gains one line about `record_mode` and where cassettes live.
- **Harness**: `.claude/settings.json` allow-list gains `Bash(pytest *)` (may already be covered by the existing `Bash(uv run *)` entry — verify in §3.1 and skip if redundant). No new deny rules; cassettes under `tests/fixtures/` are writable.

## Out of scope (deferred)

| Item | Deferred to | Why |
|---|---|---|
| Streamlit page tests via `streamlit.testing.v1.AppTest` | Phase 11 | `app.py` decomposition is the prereq; today's 1,100-line monolith is too brittle to test page-by-page. Smoke-test via the `/serve` skill instead. |
| `database.py` unit tests | Phase 12 | Storage refactor (`PRAGMA user_version` + `Storage` class) is the natural pairing. Testing today's 33 free functions locks in an API we're about to change. |
| Async / parallel source tests | Phase 13+ (if ever) | Sources are synchronous today; `ThreadPoolExecutor(4)` is the upper-bound per §0a. Cassette-level tests cover per-source correctness regardless of concurrency strategy. |
| End-to-end `startup-radar run` test | never | Would require cassettes for all sources simultaneously + a fake DB + a fake sheets sink. Value ≈ per-source tests summed; cost is much higher. |
| Cassette auto-refresh workflow | never | Cassettes drift; when a test fails because the upstream payload shape changed, a human re-records. Automation would silently mask real upstream breakage. |
| `respx` as an alternative to vcrpy | never | vcrpy already chosen in §4.1 and `pyproject.toml`. One stack, one way. |
| Mutation testing (`mutmut`) | never | Overkill for a single-user tool. Coverage + tight assertions are enough. |
| Snapshot testing of `Startup` dataclasses (`syrupy`) | never | Plain `assert startup.company_name == "Foo"` is clearer and fails more readably. |
| Load testing / rate-limit compliance tests for EDGAR | never | The `≤10 req/s` rule is enforced by runtime code, not tests. Cassettes replay once; compliance is a config-level invariant. |
| `hypothesis` property-based tests for `parse_amount_musd` | Phase 13 | Worth doing; not today. Current regex is tight enough that example-based tests catch the obvious failure modes. |
| `gitleaks` / `pip-audit` in CI | Phase 13 | Pairs with dependabot rollout. Out of scope here — ci.yml in this phase is the minimum viable gate. |

## Effort estimate

- ~3 engineering days per `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 10 (which calls out the original v1.0 estimate was low by ~40%).
- Critical path: recording the first three cassettes cleanly. EDGAR's User-Agent requirement + rate limit means one shot per calendar day before we start getting throttled; plan to record all three on day 1.
- Secondary: the gmail refactor to make `_get_service()` swappable. It's ~20 lines but the import-inside-function pattern makes monkeypatching subtle.
- Tertiary: CI workflow + coverage reporting. Small lift but requires a green first run on a throwaway branch before merging, so add a buffer day.
- Tag at end: `phase-8`.

## Prerequisites

- ✅ Phase 7 + 7.5 (commit `299d3f5`, tags `phase-7`, `phase-7.5`).
- ✅ `make ci` green at start. Working tree clean.
- ✅ `vcrpy>=6.0` already in `pyproject.toml` `[tool.uv] dev-dependencies` (added in Phase 2).
- ✅ `pytest-cov>=4.0` already in `[tool.uv] dev-dependencies`.
- No new runtime deps. No new GitHub secrets.
- No new MCP servers.

---

## 1. Files to change

| Path | Action | Notes |
|---|---|---|
| `tests/unit/` | **create** | New dir for existing `test_filters.py`, `test_smoke.py`, `parsing/`, `config/`, `test_cli_*.py`. |
| `tests/integration/` | **create** | New dir for per-source cassette-backed tests. |
| `tests/integration/__init__.py` | **create** | Empty. |
| `tests/integration/test_source_rss.py` | **create** | 3 tests (happy, empty, failure). ~80 lines. |
| `tests/integration/test_source_hackernews.py` | **create** | 3 tests. ~80 lines. |
| `tests/integration/test_source_sec_edgar.py` | **create** | 3 tests + UA-header-scrubber assertion. ~90 lines. |
| `tests/integration/test_source_gmail.py` | **create** | `_parse_body`, `_extract_body`, `_decode` + a stubbed-service `fetch()` happy path. ~100 lines. No cassettes. |
| `tests/fixtures/__init__.py` | **create** | Empty. |
| `tests/fixtures/cassettes/rss/happy.yaml` | **create** (recorded) | Real feedparser-compat response from one feed. |
| `tests/fixtures/cassettes/rss/empty.yaml` | **create** (recorded) | Feed with `<channel>` but zero `<item>` entries. |
| `tests/fixtures/cassettes/rss/http_500.yaml` | **create** (hand-edited) | Response body `<error>`, status 500. |
| `tests/fixtures/cassettes/hackernews/happy.yaml` | **create** (recorded) | Algolia response w/ ≥3 hits that match `COMPANY_SUBJECT_RE`. |
| `tests/fixtures/cassettes/hackernews/empty.yaml` | **create** (recorded) | `{"hits": []}`. |
| `tests/fixtures/cassettes/hackernews/http_500.yaml` | **create** (hand-edited) | Trigger the `except Exception` path in `fetch()`. |
| `tests/fixtures/cassettes/sec_edgar/happy.yaml` | **create** (recorded) | Real EDGAR `search-index` response w/ ≥2 Form D hits. |
| `tests/fixtures/cassettes/sec_edgar/empty.yaml` | **create** (recorded) | `{"hits": {"hits": []}}`. |
| `tests/fixtures/cassettes/sec_edgar/http_500.yaml` | **create** (hand-edited) | Proves the `resp.raise_for_status()` failure path. |
| `tests/conftest.py` | edit | Add shared `vcr_config` fixture, `vcr_cassette_dir` resolver, header scrubbers, `caplog`-friendly log capture. |
| `tests/unit/__init__.py` | **create** | Empty. |
| `tests/unit/test_filters.py` | **move** from `tests/test_filters.py` | No content change. |
| `tests/unit/test_smoke.py` | **move** from `tests/test_smoke.py` | No content change; still passes. |
| `tests/unit/parsing/` | **move** from `tests/parsing/` | No content change. |
| `tests/unit/config/` | **move** from `tests/config/` | No content change. |
| `tests/unit/test_cli_backup.py` | **move** from `tests/test_cli_backup.py` | No content change. |
| `tests/unit/test_cli_doctor.py` | **move** from `tests/test_cli_doctor.py` | No content change. |
| `tests/unit/test_cli_status.py` | **move** from `tests/test_cli_status.py` | No content change. |
| `tests/unit/test_parsing_extra.py` | **create** | Bring `parsing/funding.py` + `parsing/normalize.py` to ≥90% coverage. ~60 lines. |
| `tests/unit/test_filters_extra.py` | **create** | Edge cases on `StartupFilter` / `JobFilter` not covered by existing `test_filters.py`. ~50 lines. |
| `startup_radar/sources/gmail.py` | edit | Extract `_get_service()` hookpoint — expose as `GmailSource.service_factory` class attribute defaulting to the module-level function. Monkeypatchable for tests. ~10-line diff. |
| `pyproject.toml` | edit | `[tool.pytest.ini_options]` add `--cov=startup_radar --cov-report=term-missing --cov-report=xml`. `[tool.coverage]` sections with `fail_under=70` + per-file-ignores for `cli.py` (prints). |
| `.github/workflows/ci.yml` | **create** | PR gate: ruff check, ruff format --check, mypy, pytest w/ coverage. ~40 lines. |
| `.gitignore` | edit | Add `.coverage`, `coverage.xml`, `htmlcov/`. Already has `.pytest_cache`; verify. |
| `Makefile` | edit | `test` target: add `--cov` flags. Add `test-record` target for `VCR_RECORD_MODE=once uv run pytest tests/integration`. |
| `README.md` | edit | "Development" section: new "Running tests / re-recording cassettes" subsection per §2.8. |
| `docs/PRODUCTION_REFACTOR_PLAN.md` | edit | §0a row 10 → ✅ with tag + commit ref. |
| `.claude/CLAUDE.md` | edit | Gotchas: add one line on cassette location + record mode env var. |
| `docs/plans/phase-8.md` | **create** | This document. |

### Files explicitly NOT to touch

- `startup_radar/sources/rss.py`, `hackernews.py`, `sec_edgar.py` — tests adapt to the code, not vice versa. If a test needs a refactor to be testable, stop and re-plan.
- `database.py`, `app.py`, `connections.py` — Phase 11/12 concerns.
- `config.yaml`, `config.example.yaml` — no shape changes.
- `.github/workflows/daily.yml`, `data-branch-gc.yml` — Phase 7 work, leave as-is.
- `tests/conftest.py`'s existing `fake_repo` fixture — still used by the Phase 6 CLI tests after the move. Don't rename.

---

## 2. New/changed file shapes

### 2.1 `tests/conftest.py` diff

Add, alongside the existing `fake_repo` fixture:

```python
import os
from pathlib import Path

import pytest

CASSETTE_DIR = Path(__file__).parent / "fixtures" / "cassettes"


@pytest.fixture(scope="session")
def vcr_config() -> dict:
    """Global vcrpy config. Scrubs headers that can leak identity or secrets.

    record_mode = "none" in CI (fail if a cassette is missing) — forces
    intentional re-recording in a dev loop. Default "once" locally records
    on first run and replays thereafter.
    """
    return {
        "filter_headers": [
            ("authorization", "REDACTED"),
            ("cookie", "REDACTED"),
            ("user-agent", "startup-radar-test"),
            ("x-api-key", "REDACTED"),
        ],
        "filter_query_parameters": [("key", "REDACTED"), ("api_key", "REDACTED")],
        "record_mode": "none" if os.environ.get("CI") else "once",
        "decode_compressed_response": True,
    }


@pytest.fixture
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    """One cassette subdir per source module: tests/fixtures/cassettes/<source>/."""
    # Test file: tests/integration/test_source_rss.py → cassette dir: .../cassettes/rss/
    module = Path(request.node.fspath).stem          # "test_source_rss"
    source = module.replace("test_source_", "")      # "rss"
    return str(CASSETTE_DIR / source)
```

Notes:
- vcrpy's `pytest-recording` adapter picks up `vcr_config` and `vcr_cassette_dir` by convention — no explicit plugin registration needed beyond declaring the dev-dep.
- `record_mode=none` in CI means a missing cassette fails the test LOUDLY (rather than silently hitting the network), catching the common footgun.

### 2.2 `tests/integration/test_source_rss.py` (sketch)

```python
"""RSS source integration tests — cassette-backed, no live network."""
from __future__ import annotations

import logging

import pytest

from startup_radar.config.loader import load_config
from startup_radar.sources.rss import RSSSource


@pytest.fixture
def rss_cfg(monkeypatch: pytest.MonkeyPatch):
    """A minimal AppConfig whose rss.feeds points at a known URL we have a
    cassette for. Uses config.example.yaml as the base, overrides feeds."""
    cfg = load_config()                                   # picks up config.example.yaml defaults
    cfg.sources.rss.enabled = True
    # URL must match what's in the cassette verbatim.
    cfg.sources.rss.feeds = [_feed("https://example.test/funding.rss", name="Example")]
    return cfg


@pytest.mark.vcr()
def test_rss_happy_path(rss_cfg) -> None:
    """Cassette: rss/happy.yaml — feed with ≥2 funding-shaped items."""
    src = RSSSource()
    out = src.fetch(rss_cfg)
    assert len(out) >= 2
    first = out[0]
    assert first.company_name                      # non-empty
    assert first.source == "Example"
    assert first.amount_raised.startswith("$")     # AMOUNT_RE hit


@pytest.mark.vcr()
def test_rss_empty_feed(rss_cfg) -> None:
    """Cassette: rss/empty.yaml — valid RSS, zero items."""
    assert RSSSource().fetch(rss_cfg) == []


@pytest.mark.vcr()
def test_rss_http_500_logs_and_returns_empty(
    rss_cfg, caplog: pytest.LogCaptureFixture
) -> None:
    """Cassette: rss/http_500.yaml — feedparser returns bozo=1, we skip."""
    caplog.set_level(logging.WARNING, logger="startup_radar.sources.rss")
    out = RSSSource().fetch(rss_cfg)
    assert out == []
    # Assert on structured field, not message string (rule: testing.md).
    assert any(r.name.endswith("rss") and "fetch_failed" in r.message for r in caplog.records)
```

Notes:
- `@pytest.mark.vcr()` is from `pytest-recording` (vcrpy's pytest adapter); the cassette filename defaults to `<test_name>.yaml` under `vcr_cassette_dir`. We override per-test via `(record_mode=..., path=...)` if needed for the hand-edited 500-error cassette.
- `_feed(...)` is a small helper constructing a `FeedConfig` pydantic model — inline in the test module; no need to expose publicly.
- The `feedparser.parse(feed_url)` path doesn't go through `requests`, so vcrpy intercepts at the socket level. vcrpy does support that via `vcr.mode` but it's fiddly — fallback: monkeypatch `feedparser.parse` to read the cassette's response body and parse it directly. Decide during §3.2 after trying the native path; document the call in the test file header.

### 2.3 `tests/integration/test_source_hackernews.py` (sketch)

Same shape as §2.2 but uses `requests` directly (cassette capture is clean).

```python
@pytest.mark.vcr()
def test_hackernews_happy_path(hn_cfg) -> None:
    """Cassette: hackernews/happy.yaml — Algolia response with ≥3 company-pattern hits."""
    out = HackerNewsSource().fetch(hn_cfg)
    assert len(out) >= 3
    companies = {s.company_name for s in out}
    assert len(companies) == len(out)           # dedup via seen_titles
    # At least one hit should have stage + amount.
    assert any(s.funding_stage and s.amount_raised for s in out)


@pytest.mark.vcr()
def test_hackernews_empty(hn_cfg) -> None:
    assert HackerNewsSource().fetch(hn_cfg) == []


@pytest.mark.vcr()
def test_hackernews_http_500_logs_and_returns_empty(
    hn_cfg, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="startup_radar.sources.hackernews")
    assert HackerNewsSource().fetch(hn_cfg) == []
    assert any("fetch_failed" in r.message for r in caplog.records)
```

Gotcha: `hn_cfg.queries` must match the cassette's recorded query string — if we recorded against `"raised series"` the test config must pass the same.

### 2.4 `tests/integration/test_source_sec_edgar.py` (sketch)

Two things unique to EDGAR:
- Cassette must preserve the `User-Agent: startup-radar-template …` header in the request; the scrubber in §2.1 replaces it with `startup-radar-test` on disk. Record with the real UA, replay with anything.
- The `dateRange` params include `startdt`/`enddt` derived from `utcnow()`. That makes cassette matching on query string fragile. **Solution:** vcrpy's `match_on = ["method", "host", "path"]` (drop query-string matching for this source only).

```python
@pytest.mark.vcr(match_on=["method", "scheme", "host", "path"])
def test_sec_edgar_happy_path(edgar_cfg) -> None:
    out = SECEdgarSource().fetch(edgar_cfg)
    assert len(out) >= 2
    # Parenthetical suffix stripping from display_names.
    assert all("(" not in s.company_name for s in out)
    assert all(s.source == "SEC EDGAR" for s in out)


@pytest.mark.vcr(match_on=["method", "scheme", "host", "path"])
def test_sec_edgar_empty(edgar_cfg) -> None:
    assert SECEdgarSource().fetch(edgar_cfg) == []


@pytest.mark.vcr(match_on=["method", "scheme", "host", "path"])
def test_sec_edgar_http_500_logs_and_returns_empty(
    edgar_cfg, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="startup_radar.sources.sec_edgar")
    assert SECEdgarSource().fetch(edgar_cfg) == []
    assert any("fetch_failed" in r.message for r in caplog.records)


def test_cassette_headers_scrubbed() -> None:
    """The recorded UA must not be the real developer's identity."""
    import yaml
    cassette = yaml.safe_load(
        (CASSETTE_DIR / "sec_edgar" / "happy.yaml").read_text()
    )
    for interaction in cassette["interactions"]:
        ua = interaction["request"]["headers"].get("User-Agent", [""])[0]
        assert "startup-radar-test" in ua, f"cassette leaks real UA: {ua!r}"
```

### 2.5 `tests/integration/test_source_gmail.py` (sketch)

Gmail uses the `google-api-python-client` discovery-document stack, not plain HTTP, so cassettes don't help. Approach: pure-function tests for the parsers + an injected fake service for `fetch()`.

```python
"""Gmail source — parser units + fetch() with stubbed google API service."""

import base64
from unittest.mock import MagicMock

import pytest

from startup_radar.sources.gmail import (
    GmailSource,
    _decode,
    _extract_body,
    _parse_body,
)


# ---------- Parser units ----------

def test_decode_roundtrip() -> None:
    raw = "Hello Acme raised $5M Series A"
    encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    assert _decode(encoded) == raw


def test_decode_empty() -> None:
    assert _decode("") == ""


def test_extract_body_prefers_plain_text() -> None:
    payload = {
        "body": {},
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>html</p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("plain body")}},
        ],
    }
    assert _extract_body(payload) == "plain body"


def test_parse_body_extracts_company_and_amount() -> None:
    text = "Acme raised $5M Series A yesterday; Foo closed a Series B."
    out = _parse_body(text, subject="Daily Digest")
    companies = {s.company_name for s in out}
    assert "Acme" in companies
    assert any(s.amount_raised == "$5M" for s in out)
    assert all(s.source.startswith("Gmail:") for s in out)


# ---------- fetch() with stubbed service ----------

@pytest.fixture
def gmail_cfg(monkeypatch):
    cfg = load_config()
    cfg.sources.gmail.enabled = True
    cfg.sources.gmail.label = "funding-news"
    return cfg


def test_gmail_fetch_happy_path(gmail_cfg, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_service = _build_fake_service(
        labels=[{"id": "L1", "name": "funding-news"}],
        messages=[{"id": "m1"}, {"id": "m2"}],
        message_bodies={
            "m1": _message("Anthropic raises $750M Series D", "Anthropic raised $750M Series D."),
            "m2": _message("Cohere secures $270M", "Cohere secures $270M Series C."),
        },
    )
    monkeypatch.setattr(GmailSource, "service_factory", lambda self: fake_service)
    monkeypatch.setattr("database.is_processed", lambda *a, **k: False)
    monkeypatch.setattr("database.mark_processed", lambda *a, **k: None)

    out = GmailSource().fetch(gmail_cfg)
    assert any(s.company_name == "Anthropic" for s in out)
    assert any(s.company_name == "Cohere" for s in out)


def test_gmail_fetch_missing_label_returns_empty(
    gmail_cfg, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_service = _build_fake_service(labels=[], messages=[], message_bodies={})
    monkeypatch.setattr(GmailSource, "service_factory", lambda self: fake_service)
    caplog.set_level(logging.WARNING, logger="startup_radar.sources.gmail")
    assert GmailSource().fetch(gmail_cfg) == []
    assert any("label_missing" in r.message for r in caplog.records)
```

Helpers (`_b64`, `_message`, `_build_fake_service`) sit at the bottom of the test file; they hand-roll the subset of the Gmail API surface the source touches (`.users().labels().list()`, `.users().messages().list()`, `.users().messages().get()`).

### 2.6 `startup_radar/sources/gmail.py` diff

The minimum change to make `_get_service()` swappable by tests:

```diff
 class GmailSource(Source):
     name = "Gmail"
     enabled_key = "gmail"
+
+    def service_factory(self):
+        """Hookpoint for tests. Production: returns a real Gmail API client.
+        Tests monkeypatch this to return a MagicMock with the canned surface."""
+        return _get_service()
@@
     def fetch(self, cfg: AppConfig) -> list[Startup]:
         gmail_cfg = cfg.sources.gmail
         if not gmail_cfg.enabled:
             return []
@@
-        try:
-            service = _get_service()
+        try:
+            service = self.service_factory()
         except Exception as e:
             log.warning("source.fetch_failed", extra={"source": self.name, "err": str(e)})
             return []
```

That's it. No config-shape change, no new class attr at import time, no pytest import of google libs (factory is called lazily inside `fetch()`).

### 2.7 `.github/workflows/ci.yml` (new)

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main, 'refactor/**']

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    env:
      CI: "1"                # forces vcrpy record_mode = "none"
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Lint (ruff)
        run: uv run ruff check .

      - name: Format check (ruff)
        run: uv run ruff format --check .

      - name: Typecheck (mypy)
        run: uv run mypy

      - name: Tests (pytest + coverage)
        run: uv run pytest --cov=startup_radar --cov-report=term-missing --cov-report=xml --cov-fail-under=70

      - name: Upload coverage.xml
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-xml
          path: coverage.xml
          retention-days: 14
```

Notes:
- Single job, single Python. Matrix is overkill for a single-user tool.
- `CI=1` env is what flips `record_mode` in `tests/conftest.py`.
- No `codecov` upload yet — `coverage.xml` as an artifact is enough for this phase.
- `timeout-minutes: 10` matches the expected test runtime (cassettes replay in seconds; mypy is the slowest step).

### 2.8 `README.md` addition

```markdown
### Running tests

```bash
make ci                                     # lint + format + typecheck + tests + coverage
make test                                   # pytest only
uv run pytest tests/unit/                   # fast — no cassettes
uv run pytest tests/integration/            # cassette-backed source tests
```

#### Re-recording vcrpy cassettes

Source tests replay network interactions from `tests/fixtures/cassettes/<source>/`. To re-record after an upstream response shape changes:

```bash
rm tests/fixtures/cassettes/<source>/<name>.yaml
uv run pytest tests/integration/test_source_<source>.py::<test_name>
```

The `vcr_config` fixture records once (first run) and replays thereafter. In CI (`CI=1`), missing cassettes fail loudly rather than silently hitting the network.

**SEC EDGAR** requires a `User-Agent` with contact info — set it via the `_USER_AGENT` constant in `startup_radar/sources/sec_edgar.py` before recording. The cassette scrubber replaces it with `startup-radar-test` on disk; do not commit a cassette containing a real email address.
```

### 2.9 `pyproject.toml` diff

```diff
 [tool.pytest.ini_options]
 testpaths = ["tests"]
-addopts = "-ra -q --strict-markers"
+addopts = "-ra -q --strict-markers --cov=startup_radar --cov-report=term-missing --cov-report=xml"
 markers = [
     "integration: requires network or external services",
+    "vcr: cassette-backed test (see tests/fixtures/cassettes/)",
 ]
+
+[tool.coverage.run]
+source = ["startup_radar"]
+omit = ["startup_radar/cli.py"]         # heavy on prints + typer glue; not the core contract
+
+[tool.coverage.report]
+fail_under = 70
+show_missing = true
+skip_covered = false
+exclude_lines = [
+    "pragma: no cover",
+    "raise NotImplementedError",
+    "if __name__ == .__main__.:",
+]
```

Then in `[tool.uv] dev-dependencies` add `pytest-recording>=0.13` (the vcrpy-pytest adapter). `vcrpy` itself is already there.

### 2.10 `Makefile` diff

```diff
 test:  ## Run pytest
-	uv run pytest
+	uv run pytest

+test-unit:  ## Run only fast unit tests (no cassettes)
+	uv run pytest tests/unit/
+
+test-integration:  ## Run only cassette-backed source tests
+	uv run pytest tests/integration/
+
+test-record:  ## Re-record all cassettes (deletes existing, hits network)
+	rm -rf tests/fixtures/cassettes/*/
+	uv run pytest tests/integration/
```

Keep the existing `test` target (matches §1's `--cov` flags via `pyproject.toml addopts`; no double-flagging).

### 2.11 `.claude/CLAUDE.md` diff

```diff
 ## Gotchas
 - `data` branch (GH Actions DB store, Phase 7) — NEVER delete, rebase, or force-push from a developer machine. …
+- vcrpy cassettes live in `tests/fixtures/cassettes/<source>/`. `CI=1` sets `record_mode=none` (missing cassette → test fails loud). Locally `record_mode=once` records on first run. Re-record by deleting the yaml + rerunning the test. EDGAR cassettes scrub User-Agent to `startup-radar-test`; don't commit a real email.
```

---

## 3. Step-by-step execution

### 3.1 Pre-flight

```bash
git status                                       # clean
git log -1 --format='%h %s'                      # 299d3f5 feat(ci): GH Actions …
git tag --list 'phase-*'                         # phase-0..7.5
make ci                                          # green

# Confirm vcrpy is installed.
uv run python -c "import vcr, pytest_recording; print(vcr.__version__, pytest_recording.__version__)"

# Confirm .claude/settings.json allows pytest commands.
grep -nE '"Bash\(.*pytest|uv run' .claude/settings.json
```

If `pytest-recording` is missing, `uv add --dev pytest-recording` BEFORE any test work — skipping this wastes a day debugging "why isn't my cassette being read".

### 3.2 Move existing tests (mechanical)

```bash
git mv tests/test_smoke.py        tests/unit/test_smoke.py
git mv tests/test_filters.py      tests/unit/test_filters.py
git mv tests/test_cli_backup.py   tests/unit/test_cli_backup.py
git mv tests/test_cli_doctor.py   tests/unit/test_cli_doctor.py
git mv tests/test_cli_status.py   tests/unit/test_cli_status.py
git mv tests/parsing              tests/unit/parsing
git mv tests/config               tests/unit/config
touch tests/unit/__init__.py
touch tests/integration/__init__.py
touch tests/fixtures/__init__.py
make test                         # still green, no content changes yet
```

Existing `tests/conftest.py` (`fake_repo` fixture) stays at the root so both `unit/` and `integration/` share it. Verify Phase 6 CLI tests still find the fixture after the move.

### 3.3 Record cassettes (do all three in one sitting)

Why all three at once: EDGAR has a per-UA rate limit, RSS feeds go stale, and Algolia results drift hourly. One sitting keeps the recordings internally consistent and minimizes re-recording.

**Record on a throwaway branch, then cherry-pick the yaml onto `refactor/v2`.** Cassette recording is a messy loop — partial runs, regenerated logs, half-edited fixtures. Keep that noise out of the real phase-8 commit.

```bash
git checkout -b phase-8/record-cassettes
# ... record all cassettes per the commands below ...
git add tests/fixtures/cassettes/
git commit -m "wip: record cassettes"
git checkout refactor/v2
git checkout phase-8/record-cassettes -- tests/fixtures/cassettes/
# Now the cassettes are staged on refactor/v2; the throwaway branch is
# disposable. Delete after verification.
git branch -D phase-8/record-cassettes
```

```bash
# RSS
uv run pytest tests/integration/test_source_rss.py::test_rss_happy_path --vcr-record=once
uv run pytest tests/integration/test_source_rss.py::test_rss_empty_feed  --vcr-record=once
# Hand-author rss/http_500.yaml in a text editor (copy happy.yaml, flip status, empty body).

# Hacker News
uv run pytest tests/integration/test_source_hackernews.py::test_hackernews_happy_path --vcr-record=once
uv run pytest tests/integration/test_source_hackernews.py::test_hackernews_empty     --vcr-record=once
# Hand-author hackernews/http_500.yaml.

# SEC EDGAR (last, in case we trip the UA rate limit)
uv run pytest tests/integration/test_source_sec_edgar.py::test_sec_edgar_happy_path --vcr-record=once
uv run pytest tests/integration/test_source_sec_edgar.py::test_sec_edgar_empty     --vcr-record=once
# Hand-author sec_edgar/http_500.yaml.
```

For the "empty" cassette on sources whose upstream always returns data: after recording, hand-edit the cassette's response body to the empty-shape equivalent. Document this in a header comment inside the yaml.

After recording, verify no secrets leaked:

```bash
grep -RE 'Bearer [A-Za-z0-9]|@(gmail|outlook)\.com' tests/fixtures/cassettes/
# expect zero hits
```

### 3.4 Write integration tests (parallel, 3 files)

Spawn three `source-implementer`-style subagents (or implement serially if the main agent has the context — tests are short). Files are independent: no shared fixtures between them beyond `conftest.py`.

Run `uv run pytest tests/integration/ -v` after each file lands — must be green before proceeding.

### 3.5 Write Gmail parser + stubbed-service tests

Sequential, single file. Ensure the `service_factory` diff in `startup_radar/sources/gmail.py` ships in the same commit as the test file — the test monkeypatches on that attribute.

Smoke:

```bash
uv run pytest tests/integration/test_source_gmail.py -v
```

### 3.6 Expand unit tests to coverage targets

```bash
uv run pytest tests/unit/ --cov=startup_radar --cov-report=term-missing | tee /tmp/cov.txt
```

Read the missing-line report; add targeted tests in `tests/unit/test_parsing_extra.py` and `tests/unit/test_filters_extra.py` to close gaps in `parsing/` and `filters.py`. Target: ≥90% on those modules.

### 3.7 Wire the CI workflow

Write `.github/workflows/ci.yml` per §2.7. Smoke locally:

```bash
# Lint the workflow YAML.
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"

# Simulate CI locally.
CI=1 uv run pytest --cov=startup_radar --cov-fail-under=70
```

Push the branch, open a draft PR, confirm `CI` job is green before merging. If the coverage threshold fails in CI but passes locally, the usual cause is an OS-specific path in a test — debug by downloading the `coverage-xml` artifact.

### 3.8 Docs + harness (parallel)

Parallel `Edit` calls:
- `README.md` (§2.8 subsection)
- `pyproject.toml` (§2.9)
- `Makefile` (§2.10)
- `.claude/CLAUDE.md` (§2.11)
- `docs/PRODUCTION_REFACTOR_PLAN.md` (§0a row 10 → ✅)
- `.gitignore` (`.coverage`, `coverage.xml`, `htmlcov/`)

### 3.9 Ship + tag

```bash
make ci                                          # green
/ship                                            # sanctioned commit path
```

Suggested commit message:

```
feat(tests): vcrpy cassettes + real source tests + CI workflow

Replaces the Phase 0 smoke placeholder with a real integration-test
layer for every source. Three cassette-backed tests per HTTP source
(happy, empty, failure) + stubbed-Gmail-service tests for the OAuth
path, plus unit-coverage expansions to hit the per-module targets
from .claude/rules/testing.md (parsing/filters ≥90%, sources ≥70%).

- tests/ restructured into unit/ + integration/ (existing tests
  moved mechanically; no content change).
- tests/fixtures/cassettes/<source>/ — 3 cassettes per source, UA
  and auth headers scrubbed; CI=1 forces record_mode=none.
- startup_radar/sources/gmail.py: extract _get_service() to
  GmailSource.service_factory hookpoint for test injection; no
  behavior change.
- .github/workflows/ci.yml: PR gate — ruff, format-check, mypy,
  pytest w/ coverage. Uploads coverage.xml as a 14-day artifact.
- Makefile: test-unit, test-integration, test-record targets.
- pyproject.toml: --cov flags on pytest; [tool.coverage] with
  fail_under=70; pytest-recording dev-dep.

Closes row 10 in docs/PRODUCTION_REFACTOR_PLAN.md §0a.
```

After merge to main:

```bash
git tag phase-8
git push origin phase-8
gh workflow run ci.yml                           # sanity check
```

---

## 4. Verification checklist

```bash
# 1. Unit + integration tests all green, locally.
make ci

# 2. CI-like environment variables honored.
CI=1 uv run pytest tests/integration/        # missing cassette → test FAILS, not hits network

# 3. Coverage thresholds met.
uv run pytest --cov=startup_radar --cov-report=term-missing | grep TOTAL
# → percentage ≥70; parsing/ + filters.py lines ≥90%.

# 4. Cassettes contain no secrets.
grep -RE 'Bearer |@gmail\.com|@outlook\.com|@anthropic\.com' tests/fixtures/cassettes/ || echo "clean"

# 5. EDGAR cassette UA scrubbed.
uv run pytest tests/integration/test_source_sec_edgar.py::test_cassette_headers_scrubbed -v

# 6. Gmail tests do NOT import google.* at module load.
uv run python -c "import tests.integration.test_source_gmail"
# → no ImportError even without `google-api-python-client` installed in test env.

# 7. CI workflow parses.
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
which actionlint && actionlint .github/workflows/*.yml

# 8. CI workflow green on a draft PR.
gh pr create --draft ...; gh pr checks --watch

# 9. Moving files did not break existing tests.
uv run pytest tests/unit/test_cli_backup.py tests/unit/test_cli_doctor.py tests/unit/test_cli_status.py -v

# 10. Re-recording round-trip works.
rm tests/fixtures/cassettes/hackernews/happy.yaml
uv run pytest tests/integration/test_source_hackernews.py::test_hackernews_happy_path
# → re-records cleanly; second run replays.
git checkout -- tests/fixtures/cassettes/hackernews/happy.yaml
```

---

## 5. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | vcrpy doesn't intercept `feedparser`'s socket-level reads | Medium | RSS tests can't record | Fall back: monkeypatch `feedparser.parse` to read the cassette body from disk and parse it. Decision point in §3.3. Document in the test file header so future-Claude doesn't revert. |
| 2 | Cassette drift: upstream (Algolia, EDGAR) changes response shape; tests fail in CI with no upstream change on our side | Medium (6-12 month window) | Red main; human re-records | `test-record` Makefile target makes re-recording a one-liner. Add a note to CLAUDE.md gotchas (§2.11). Accept as cost of integration tests. |
| 3 | Recorded cassette contains developer PII (email in UA, IP in X-Forwarded-For, personal OAuth scopes in Gmail quota headers) | High pre-scrubber, low post | Leak real identity to public repo | Global `filter_headers` in `vcr_config` + the `test_cassette_headers_scrubbed` assertion + the grep in §3.3 verification step. Triple-layer check. |
| 4 | EDGAR rate-limits the developer's IP during recording (≥10 req/s) | Low (3 requests total) | Recording fails mid-session | Record all EDGAR cassettes last, one at a time with `sleep 1` between. If rate-limited, wait 10 minutes and retry. |
| 5 | Gmail `service_factory` hookpoint pattern conflicts with a future OAuth-refresh refactor | Medium | Test monkeypatch breaks silently | Factory is instance-level (`self.service_factory()`), not class-level — so a subclass override works. Document in a one-liner on the method's docstring. |
| 6 | `--cov-fail-under=70` is too aggressive and blocks CI on trivially untested code (e.g. new CLI command) | Medium | PR merges blocked | `[tool.coverage.run].omit = ["startup_radar/cli.py"]` already excludes the CLI. If another hot spot emerges, add to `omit` with a one-line PR rationale. Do NOT lower the global threshold below 70. |
| 7 | `tests/integration/` tests run in CI but `CI=1` env not forwarded to parallel pytest workers (if `pytest-xdist` added later) | Low (no xdist today) | Worker re-records instead of failing | Not a concern today — phase doesn't add xdist. Flag in Phase 13 if parallelism is introduced. |
| 8 | The empty-response hand-edited cassettes go stale relative to upstream schema | Low | Test passes but validates a dead schema | Re-record happy-path cassette on schema change; hand-edit empty from the new happy-path shape. One-paragraph "re-recording" section in README covers the procedure. |
| 9 | `test_cassette_headers_scrubbed` fires on yaml structure vcrpy silently changed between versions | Low (vcrpy pinned to `>=6.0`) | False positive in CI | Pin `vcrpy` more tightly if we see churn: `vcrpy>=6.0,<7.0`. Defer the pin unless it bites. |
| 10 | Gmail tests import `google.auth.*` at module load despite the factory hookpoint (indirect via `_get_service`) | Low | Tests fail in CI if `[google]` extra not installed | Verification step #6 in §4. Function-level import inside `_get_service` keeps the module importable without google libs. |
| 11 | `pytest-recording` doesn't fail when a cassette exists on disk but the request doesn't match (it falls back to record) | Medium | Cassette drift goes undetected | `CI=1` + `record_mode=none` turns "no match" into a hard error. Dev loop uses `once` (new interactions append); `all` for forced re-record. Document all three modes in README. |
| 12 | `actions/checkout@v4` + vcrpy yaml files exceed GH Actions' workspace size limit | Very low | CI fails | Cassettes are tiny (KB-scale); aggregate size <1 MB. Not a realistic concern. |
| 13 | CI runs the SEC EDGAR test, which replays a cassette that includes the user's real email in the UA because scrubber regex missed a case | Low (if scrubber correct) | Leak via public CI logs | The `test_cassette_headers_scrubbed` meta-test fails BEFORE the test that would log the UA. Green ci.yml is proof no leak. |
| 14 | `make test-record` deletes cassettes with a wildcard and someone runs it on main | Low | Lost cassettes; forced re-record | `make test-record` target runs `rm -rf tests/fixtures/cassettes/*/`. Add a `@read -p "confirm? (y/N) " ok && [ "$$ok" = "y" ]` prompt. |
| 15 | The move from `tests/` to `tests/unit/` breaks the Phase-6 `fake_repo` fixture's relative path calculations | Medium | Phase 6 CLI tests fail | `fake_repo` uses `Path(__file__).resolve().parent.parent` → `REPO_ROOT`. Moving `conftest.py` DOES NOT happen — only test files move. `REPO_ROOT` still resolves. Verify in §3.2. |

---

## 6. Done criteria

- [ ] `tests/unit/` and `tests/integration/` dirs exist; existing tests moved with `git mv`.
- [ ] `tests/fixtures/cassettes/{rss,hackernews,sec_edgar}/` each contain ≥3 cassettes (happy, empty, failure).
- [ ] Each HTTP source has ≥3 tests in `tests/integration/test_source_<name>.py`, passing with `CI=1`.
- [ ] Gmail test file passes without `google-api-python-client` being importable (factory is lazy).
- [ ] `make ci` green locally.
- [ ] `.github/workflows/ci.yml` exists and is green on a draft PR.
- [ ] Coverage ≥70% overall; ≥90% on `startup_radar/parsing/` and `startup_radar/filters.py` (verify in `term-missing` report).
- [ ] Cassette scrubber assertion (`test_cassette_headers_scrubbed`) green.
- [ ] No email addresses, Bearer tokens, or OAuth refresh tokens in `tests/fixtures/cassettes/`.
- [ ] `pyproject.toml` addopts include `--cov`; `[tool.coverage]` sections present.
- [ ] `Makefile` has `test-unit`, `test-integration`, `test-record` targets.
- [ ] `README.md` "Running tests" subsection exists with re-record instructions.
- [ ] `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 10 → ✅ with tag + commit ref.
- [ ] `.claude/CLAUDE.md` gotchas section has the cassette + `CI=1` line.
- [ ] Commit tagged `phase-8`.

---

## 7. What this enables

- **Phase 9 (deferred — not in §0a):** nothing. Phase 8 is a hard prerequisite for every subsequent refactor — you can't safely change sources, filters, or parsing without a test harness that catches regressions.
- **Phase 10 (dashboard decomposition, §0a row 11):** the `streamlit.testing.v1.AppTest` pattern lands here. The `tests/integration/` dir already exists; Streamlit tests slot in as `tests/integration/test_app_<page>.py`.
- **Phase 11 (storage class + migrator, §0a row 12):** the `Storage` class refactor can be red-green-refactored against a new `tests/unit/test_storage.py` from day one, instead of retrofitted. Migrator gets a `test_user_version_bump.py` against a fixture DB.
- **Phase 12 (structlog + retries + counters, §0a row 13):** `caplog`-based assertions in the integration tests ALREADY exercise the logger; swapping in structlog is a drop-in. Retry logic gets tested by adding a second interaction to the failure-mode cassette (first call 500, second 200).
- **Phase 13+ (Dockerfile, MkDocs):** CI workflow becomes the natural place to wire `docker build` smoke and mkdocs-material's `mkdocs build --strict`. Extend ci.yml; no new workflow.
- **`/add-source` skill (deferred from Phase 7.5):** can now land because the source-implementer subagent has a test scaffolding pattern to follow — the new skill generates a source module + 3 test skeletons + empty cassette dir in one pass.
