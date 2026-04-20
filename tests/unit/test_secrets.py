"""Tests for startup_radar.config.secrets — env-var loading + aliases."""

from __future__ import annotations

import pytest

from startup_radar.config import secrets
from startup_radar.config.secrets import Secrets


def _fresh(monkeypatch: pytest.MonkeyPatch, **env: str) -> Secrets:
    """Clear any existing env so each case starts clean, set the ones we want,
    drop the cache, and return a fresh `Secrets` instance."""
    for var in ("STARTUP_RADAR_LOG_JSON", "CI", "STARTUP_RADAR_CI", "SENTRY_DSN"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    secrets.cache_clear()  # type: ignore[attr-defined]
    return secrets()


def test_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _fresh(monkeypatch)
    assert s.log_json is False
    assert s.ci is False
    assert s.sentry_dsn is None


def test_log_json_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _fresh(monkeypatch, STARTUP_RADAR_LOG_JSON="1")
    assert s.log_json is True


def test_ci_alias_unprefixed(monkeypatch: pytest.MonkeyPatch) -> None:
    """`CI` (standard CI marker) resolves via AliasChoices, no prefix required."""
    s = _fresh(monkeypatch, CI="1")
    assert s.ci is True


def test_sentry_dsn_alias_unprefixed(monkeypatch: pytest.MonkeyPatch) -> None:
    """`SENTRY_DSN` follows Sentry's ecosystem convention — no prefix."""
    dsn = "https://abc@o1.ingest.sentry.io/42"
    s = _fresh(monkeypatch, SENTRY_DSN=dsn)
    assert s.sentry_dsn == dsn


def test_unknown_vars_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """`extra="ignore"` — `.env` may contain shell-only vars like
    `STARTUP_RADAR_SHIP=1`; those must not raise."""
    s = _fresh(monkeypatch, STARTUP_RADAR_SHIP="1", STARTUP_RADAR_FOO="bar")
    assert s.log_json is False
    assert not hasattr(s, "foo")
    assert not hasattr(s, "ship")


def test_cache_returns_same_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    _fresh(monkeypatch)
    assert secrets() is secrets()


def test_cache_clear_reloads(monkeypatch: pytest.MonkeyPatch) -> None:
    _fresh(monkeypatch)
    assert secrets().log_json is False
    monkeypatch.setenv("STARTUP_RADAR_LOG_JSON", "1")
    secrets.cache_clear()  # type: ignore[attr-defined]
    assert secrets().log_json is True
