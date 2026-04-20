"""record_run / last_run / failure_streak round-trip."""

from __future__ import annotations

from pathlib import Path

from startup_radar.storage.sqlite import SqliteStorage


def _mk(tmp_path: Path) -> SqliteStorage:
    s = SqliteStorage(tmp_path / "x.db")
    s.migrate_to_latest()
    return s


def test_record_and_last_run(tmp_path: Path) -> None:
    s = _mk(tmp_path)
    s.record_run(
        "rss",
        started_at="2026-04-19T12:00:00",
        ended_at="2026-04-19T12:00:02",
        items_fetched=5,
        items_kept=3,
        error=None,
        user_version_at_run=2,
    )
    lr = s.last_run("rss")
    assert lr is not None
    assert lr["items_fetched"] == 5
    assert lr["items_kept"] == 3
    assert lr["error"] is None
    assert lr["user_version_at_run"] == 2
    s.close()


def test_failure_streak_counts_from_newest(tmp_path: Path) -> None:
    s = _mk(tmp_path)
    for err in (None, "boom", "boom"):
        s.record_run(
            "hackernews",
            started_at="t",
            ended_at="t",
            items_fetched=0,
            items_kept=0,
            error=err,
            user_version_at_run=2,
        )
    assert s.failure_streak("hackernews") == 2
    s.close()


def test_failure_streak_resets_on_success(tmp_path: Path) -> None:
    s = _mk(tmp_path)
    for err in ("boom", "boom", None):
        s.record_run(
            "sec_edgar",
            started_at="t",
            ended_at="t",
            items_fetched=0,
            items_kept=0,
            error=err,
            user_version_at_run=2,
        )
    assert s.failure_streak("sec_edgar") == 0
    s.close()


def test_last_run_none_for_unknown_source(tmp_path: Path) -> None:
    s = _mk(tmp_path)
    assert s.last_run("gmail") is None
    assert s.failure_streak("gmail") == 0
    s.close()


def test_user_version_at_2_after_migrate(tmp_path: Path) -> None:
    """0002_runs_table bumps user_version to 2 after migrate_to_latest."""
    s = _mk(tmp_path)
    assert s.user_version() == 2
    s.close()
