"""Gmail source — parser units (no cassettes, run immediately) + stubbed-service fetch() tests.

Parser unit tests import the module-level helpers (`_decode`, `_extract_body`,
`_parse_body`) directly — they need no cassettes and no google libs.

The `fetch()` tests monkeypatch `GmailSource.service_factory` to return a
hand-rolled MagicMock mimicking the subset of the Gmail API surface the
source touches. They're skipped at the class level pending Phase 8 wiring.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from startup_radar.config import AppConfig
from startup_radar.sources.gmail import (
    GmailSource,
    _decode,
    _extract_body,
    _parse_body,
)

EXAMPLE = Path(__file__).resolve().parents[2] / "config.example.yaml"


def _cfg() -> AppConfig:
    with open(EXAMPLE, encoding="utf-8") as f:
        return AppConfig.model_validate(yaml.safe_load(f))


def _b64(s: str) -> str:
    # Keep padding: the source's _decode uses urlsafe_b64decode which requires it.
    # Real Gmail API strips '=' but _decode re-pads in a production fix; for the
    # test we simply don't strip.
    return base64.urlsafe_b64encode(s.encode()).decode()


# ---------- Parser units (always run — no cassettes, no service) ----------


def test_decode_roundtrip() -> None:
    raw = "Hello Acme raised $5M Series A"
    encoded = _b64(raw)
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


def test_extract_body_direct_body_data() -> None:
    payload = {"body": {"data": _b64("top-level body")}}
    assert _extract_body(payload) == "top-level body"


def test_extract_body_empty_payload() -> None:
    assert _extract_body({}) == ""


def test_parse_body_extracts_company_and_amount() -> None:
    text = "Acme raised $5M Series A yesterday. More news follows."
    out = _parse_body(text, subject="Daily Digest")
    assert out, "expected at least one Startup"
    companies = {s.company_name for s in out}
    assert "Acme" in companies
    assert any(s.amount_raised == "$5M" for s in out)
    assert all(s.source.startswith("Gmail:") for s in out)


def test_parse_body_empty_returns_empty() -> None:
    assert _parse_body("", subject="Nothing") == []


# ---------- fetch() with stubbed service ----------


def _message(subject: str, body: str) -> dict:
    """Construct a Gmail API full-format message dict."""
    return {
        "payload": {
            "headers": [{"name": "Subject", "value": subject}],
            "body": {"data": _b64(body)},
            "parts": [],
        }
    }


def _build_fake_service(
    *,
    labels: list[dict],
    messages: list[dict],
    message_bodies: dict[str, dict],
) -> MagicMock:
    """Hand-roll the subset of the Gmail API surface the source touches.

    Surface: service.users().labels().list(userId=...).execute()
             service.users().messages().list(userId=..., labelIds=..., maxResults=...).execute()
             service.users().messages().get(userId=..., id=..., format=...).execute()
    """
    service = MagicMock()
    users = service.users.return_value

    users.labels.return_value.list.return_value.execute.return_value = {"labels": labels}

    users.messages.return_value.list.return_value.execute.return_value = {"messages": messages}

    def _get(userId: str, id: str, format: str) -> MagicMock:
        inner = MagicMock()
        inner.execute.return_value = message_bodies[id]
        return inner

    users.messages.return_value.get.side_effect = _get
    return service


class TestGmailFetchStubbed:
    """fetch() tests that stub `GmailSource.service_factory` with a fake
    Gmail API client. No cassettes — google-api-python-client uses a
    discovery-document stack that doesn't play well with HTTP replay."""

    @pytest.fixture
    def gmail_cfg(self) -> AppConfig:
        cfg = _cfg()
        cfg.sources.gmail.enabled = True
        cfg.sources.gmail.label = "funding-news"
        return cfg

    def test_gmail_fetch_happy_path(
        self,
        gmail_cfg: AppConfig,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from startup_radar.storage.sqlite import SqliteStorage

        fake = _build_fake_service(
            labels=[{"id": "L1", "name": "funding-news"}],
            messages=[{"id": "m1"}, {"id": "m2"}],
            message_bodies={
                "m1": _message(
                    "Anthropic raises $750M Series D",
                    "Anthropic raised $750M Series D.",
                ),
                "m2": _message(
                    "Cohere secures $270M",
                    "Cohere secures $270M Series C.",
                ),
            },
        )
        monkeypatch.setattr(GmailSource, "service_factory", lambda self: fake)
        storage = SqliteStorage(tmp_path / "gmail.db")
        storage.migrate_to_latest()

        out = GmailSource().fetch(gmail_cfg, storage=storage)
        companies = {s.company_name for s in out}
        assert "Anthropic" in companies
        assert "Cohere" in companies
        # Second fetch should find nothing new — dedup path
        assert GmailSource().fetch(gmail_cfg, storage=storage) == []
        storage.close()

    def test_gmail_fetch_missing_label_returns_empty(
        self,
        gmail_cfg: AppConfig,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        tmp_path,
    ) -> None:
        from startup_radar.storage.sqlite import SqliteStorage

        fake = _build_fake_service(labels=[], messages=[], message_bodies={})
        monkeypatch.setattr(GmailSource, "service_factory", lambda self: fake)
        storage = SqliteStorage(tmp_path / "gmail.db")
        storage.migrate_to_latest()
        caplog.set_level(logging.WARNING, logger="startup_radar.sources.gmail")

        assert GmailSource().fetch(gmail_cfg, storage=storage) == []
        assert any("label_missing" in r.message for r in caplog.records)
        storage.close()

    def test_gmail_fetch_retries_on_labels_list(
        self,
        gmail_cfg: AppConfig,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """labels().list().execute() throws twice then returns → retry wraps it."""
        from startup_radar.storage.sqlite import SqliteStorage

        fake = _build_fake_service(
            labels=[{"id": "L1", "name": "funding-news"}],
            messages=[],
            message_bodies={},
        )

        calls = {"n": 0}
        real_execute = fake.users.return_value.labels.return_value.list.return_value.execute

        def _flaky_execute() -> dict:
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("transient")
            return real_execute.return_value

        fake.users.return_value.labels.return_value.list.return_value.execute = _flaky_execute

        monkeypatch.setattr(GmailSource, "service_factory", lambda self: fake)
        storage = SqliteStorage(tmp_path / "gmail.db")
        storage.migrate_to_latest()

        assert GmailSource().fetch(gmail_cfg, storage=storage) == []
        assert calls["n"] == 3
        storage.close()
