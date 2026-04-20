"""Retry helper tests. All hermetic — ``time.sleep`` is monkeypatched."""

from __future__ import annotations

import pytest

from startup_radar.sources._retry import retry


def test_returns_on_first_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fn() -> int:
        calls["n"] += 1
        return 42

    monkeypatch.setattr("startup_radar.sources._retry._sleep", lambda *_: None)
    assert retry(fn) == 42
    assert calls["n"] == 1


def test_retries_twice_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fn() -> int:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("flaky")
        return 7

    sleeps: list[float] = []
    monkeypatch.setattr("startup_radar.sources._retry._sleep", lambda d: sleeps.append(d))

    assert retry(fn) == 7
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_exhausts_attempts_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fn() -> int:
        raise TimeoutError("forever")

    monkeypatch.setattr("startup_radar.sources._retry._sleep", lambda *_: None)
    with pytest.raises(TimeoutError):
        retry(fn, attempts=3)


def test_only_retries_listed_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    def fn() -> int:
        raise ValueError("not retryable")

    monkeypatch.setattr("startup_radar.sources._retry._sleep", lambda *_: None)
    with pytest.raises(ValueError):
        retry(fn, on=(ConnectionError,), attempts=3)


def test_backoff_tuple_extends_by_last_value(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fn() -> int:
        calls["n"] += 1
        raise ConnectionError

    sleeps: list[float] = []
    monkeypatch.setattr("startup_radar.sources._retry._sleep", lambda d: sleeps.append(d))

    with pytest.raises(ConnectionError):
        retry(fn, attempts=5, backoff=(0.1, 0.2))

    assert sleeps == [0.1, 0.2, 0.2, 0.2]
    assert calls["n"] == 5
