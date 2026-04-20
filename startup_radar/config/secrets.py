"""Environment-variable secrets loader. Single entry point for `.env` + `os.environ`.

This module is the ONLY place in `startup_radar/` allowed to read environment
variables (see `.claude/CLAUDE.md` invariants). Every other call-site imports
the cached `secrets()` accessor below.

Fields use the `STARTUP_RADAR_` prefix by default. Two exceptions:

- `ci` reads `CI` (standard across CI systems) via `AliasChoices`.
- `sentry_dsn` reads plain `SENTRY_DSN` — Sentry ecosystem convention.

Test-seam pattern:

    def test_log_json(monkeypatch):
        monkeypatch.setenv("STARTUP_RADAR_LOG_JSON", "1")
        secrets.cache_clear()
        assert secrets().log_json is True

`tests/conftest.py` already autouse-clears the cache after each test, so the
`cache_clear()` call above is only needed when a single test wants to observe
a fresh instance mid-test.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STARTUP_RADAR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    log_json: bool = False
    ci: bool = Field(
        default=False,
        validation_alias=AliasChoices("CI", "STARTUP_RADAR_CI"),
    )
    sentry_dsn: str | None = Field(
        default=None,
        validation_alias="SENTRY_DSN",
    )


@lru_cache(maxsize=1)
def _cached() -> Secrets:
    return Secrets()


def secrets() -> Secrets:
    return _cached()


def cache_clear() -> None:
    _cached.cache_clear()


secrets.cache_clear = cache_clear  # type: ignore[attr-defined]
