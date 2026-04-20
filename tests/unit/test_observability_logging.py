"""structlog pipeline tests. Use capsys for both JSON and pretty outputs."""

from __future__ import annotations

import json
import logging

import pytest
import structlog

from startup_radar.observability.logging import configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset() -> None:
    """Clear contextvars between tests to avoid bleed-through."""
    structlog.contextvars.clear_contextvars()


def test_json_mode_emits_json_object(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json=True)
    log = get_logger("t")
    log.info("thing.happened", x=1, y="two")

    err = capsys.readouterr().err.strip()
    assert err, "expected a JSON log line"
    record = json.loads(err)
    assert record["event"] == "thing.happened"
    assert record["level"] == "info"
    assert record["x"] == 1
    assert record["y"] == "two"
    assert "timestamp" in record


def test_pretty_mode_renders_event_and_fields(capsys: pytest.CaptureFixture[str]) -> None:
    import re

    configure_logging(json=False)
    log = get_logger("t")
    log.info("thing.happened", x=1)
    raw = capsys.readouterr().err
    err = re.sub(r"\x1b\[[0-9;]*m", "", raw)  # strip ANSI color codes
    assert "thing.happened" in err
    assert "x=1" in err


def test_contextvars_propagate(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json=True)
    log = get_logger("t")
    structlog.contextvars.bind_contextvars(source="rss")
    try:
        log.info("source.fetch")
    finally:
        structlog.contextvars.clear_contextvars()
    record = json.loads(capsys.readouterr().err.strip())
    assert record["source"] == "rss"


def test_stdlib_logger_flows_through(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json=True)
    logging.getLogger("test.library").info("adapter.send")
    err = capsys.readouterr().err.strip()
    assert err
    record = json.loads(err)
    assert record["event"] == "adapter.send"
