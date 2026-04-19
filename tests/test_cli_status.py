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
