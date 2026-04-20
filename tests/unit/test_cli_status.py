"""Tests for `startup-radar status`. Pure read, no network."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from startup_radar.cli import app

runner = CliRunner()


def test_status_reports_zero_rows_on_fresh_db(fake_repo: Path) -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "DB rows:" in result.output
    assert "startups=0" in result.output


def test_status_reports_nonzero_after_insert(fake_repo: Path) -> None:
    db = fake_repo / "startup_radar.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("INSERT INTO startups (company_name) VALUES ('X'), ('Y')")
    result = runner.invoke(app, ["status"])
    assert "startups=2" in result.output


def test_status_last_run_age(fake_repo: Path) -> None:
    logs = fake_repo / "logs"
    (logs / "2026-04-19.log").write_text("run log")
    result = runner.invoke(app, ["status"])
    assert "Last run:" in result.output
    assert "ago" in result.output


def test_status_repo_root_helper_points_at_real_repo() -> None:
    """Sanity check: unpatched _repo_root must resolve to a real repo."""
    from startup_radar.cli import _repo_root

    root = _repo_root()
    assert (root / "pyproject.toml").exists()
    assert (root / "startup_radar").is_dir()


def test_status_shows_per_source_health_block(fake_repo: Path) -> None:
    """`status` renders a `Per-source health:` block when config loads."""
    result = runner.invoke(app, ["status"])
    assert "Per-source health:" in result.output


def test_status_shows_failure_streak(fake_repo: Path, monkeypatch) -> None:
    """A source with >0 failed runs surfaces `N failures` in the status block."""
    import yaml

    from startup_radar.models import JobMatch  # noqa: F401  (ensure module import)
    from startup_radar.storage.sqlite import SqliteStorage

    cfg_path = fake_repo / "config.yaml"
    data = yaml.safe_load(cfg_path.read_text())
    data["sources"]["rss"]["enabled"] = True
    cfg_path.write_text(yaml.safe_dump(data))

    db = fake_repo / "startup_radar.db"
    db.unlink()
    s = SqliteStorage(db)
    s.migrate_to_latest()
    s.record_run(
        "rss",
        started_at="2026-04-19T00:00:00",
        ended_at="2026-04-19T00:00:01",
        items_fetched=0,
        items_kept=0,
        error="BoomError",
        user_version_at_run=s.user_version(),
    )
    s.close()

    result = runner.invoke(app, ["status"])
    assert "rss" in result.output
    assert "1 failures" in result.output
