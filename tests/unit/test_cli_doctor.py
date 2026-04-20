"""Tests for `startup-radar doctor`. Fast mode only — no network."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from startup_radar.cli import app

runner = CliRunner()


def test_doctor_fast_renders_report(fake_repo: Path) -> None:
    result = runner.invoke(app, ["doctor"])
    # Exit may be 0 or 1 depending on the fake_repo's source config;
    # at minimum the header renders and Python-version row is ✓.
    assert "doctor" in result.output
    assert "Python version" in result.output
    assert "✓ Python version" in result.output


def test_doctor_missing_config_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("startup_radar.cli._repo_root", lambda: tmp_path)
    monkeypatch.setattr("startup_radar.config.loader.CONFIG_FILE", tmp_path / "config.yaml")
    monkeypatch.setattr(
        "startup_radar.config.loader.EXAMPLE_FILE", tmp_path / "config.example.yaml"
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "config.yaml" in result.output


def test_doctor_fast_does_not_hit_network(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure default `doctor` invocation makes no HTTP calls."""

    def _fake(*a: object, **kw: object) -> None:
        raise AssertionError("network called in fast mode")

    monkeypatch.setattr("requests.head", _fake)
    monkeypatch.setattr("requests.get", _fake)

    result = runner.invoke(app, ["doctor"])
    # Must render without the fake raising; exit code can be 0 or 1.
    assert "doctor" in result.output


def test_doctor_network_invokes_healthcheck(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--network flag triggers per-source healthchecks with network=True."""
    from startup_radar.sources.registry import SOURCES

    seen: list[bool] = []

    for src in SOURCES.values():
        original = src.healthcheck

        def _wrap(cfg: object, *, network: bool = False, _orig=original) -> tuple[bool, str]:
            seen.append(network)
            return (True, "stubbed")

        monkeypatch.setattr(src, "healthcheck", _wrap)

    runner.invoke(app, ["doctor", "--network"])
    assert any(seen), "no healthchecks invoked"
    assert all(seen), "at least one healthcheck ran with network=False"


def test_doctor_warns_on_failure_streak(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """>2 consecutive failed runs surface as a ⚠ streak row. Exit stays 0-or-fail
    driven by the other checks, never incremented by the streak warning itself."""
    import yaml

    from startup_radar.sources.registry import SOURCES
    from startup_radar.storage.sqlite import SqliteStorage

    cfg_path = fake_repo / "config.yaml"
    data = yaml.safe_load(cfg_path.read_text())
    data["sources"]["rss"]["enabled"] = True
    cfg_path.write_text(yaml.safe_dump(data))

    db = fake_repo / "startup_radar.db"
    db.unlink()
    s = SqliteStorage(db)
    s.migrate_to_latest()
    for i in range(3):
        s.record_run(
            "rss",
            started_at=f"2026-04-1{i}T00:00:00",
            ended_at=f"2026-04-1{i}T00:00:01",
            items_fetched=0,
            items_kept=0,
            error="BoomError",
            user_version_at_run=s.user_version(),
        )
    s.close()

    # Stub healthchecks so they don't add their own ✗ that confuses the assertion.
    for src in SOURCES.values():
        monkeypatch.setattr(src, "healthcheck", lambda *_a, **_kw: (True, "stubbed"), raising=False)

    result = runner.invoke(app, ["doctor"])
    assert "source.rss.streak" in result.output
    assert "3 consecutive failed runs" in result.output
