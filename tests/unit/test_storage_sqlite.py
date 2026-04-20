"""Smoke test for SqliteStorage. Round-trips two startups + one job_match
through the real schema on tmp-path storage. Intentionally minimal —
per-method coverage lives in the integration tests once they're pointed at
the new class.
"""

from __future__ import annotations

from pathlib import Path

from startup_radar.models import JobMatch, Startup
from startup_radar.storage.sqlite import SqliteStorage


def test_round_trip(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "x.db")
    storage.migrate_to_latest()

    inserted = storage.insert_startups(
        [
            Startup(company_name="Acme", source="rss"),
            Startup(company_name="Globex", source="hackernews"),
        ]
    )
    assert inserted == 2

    df = storage.get_all_startups()
    assert set(df["Company Name"]) == {"Acme", "Globex"}

    storage.insert_job_matches(
        [JobMatch(company_name="Acme", role_title="Staff Engineer", source="rss")]
    )
    jobs = storage.get_all_job_matches()
    assert len(jobs) == 1
    assert jobs.iloc[0]["Role"] == "Staff Engineer"

    storage.close()


def test_user_version_after_migrate(tmp_path: Path) -> None:
    s = SqliteStorage(tmp_path / "x.db")
    s.migrate_to_latest()
    assert s.user_version() == 2
    assert s.migrate_to_latest() == []
    s.close()


def test_insert_startups_is_idempotent_on_duplicate(tmp_path: Path) -> None:
    s = SqliteStorage(tmp_path / "x.db")
    s.migrate_to_latest()
    first = s.insert_startups([Startup(company_name="Acme", source="rss")])
    second = s.insert_startups([Startup(company_name="Acme", source="rss")])
    assert first == 1
    assert second == 0
    s.close()


def test_processed_items_roundtrip(tmp_path: Path) -> None:
    s = SqliteStorage(tmp_path / "x.db")
    s.migrate_to_latest()
    assert s.is_processed("gmail", "m1") is False
    s.mark_processed("gmail", ["m1", "m2"])
    assert s.is_processed("gmail", "m1") is True
    assert s.is_processed("gmail", "m3") is False
    s.close()
