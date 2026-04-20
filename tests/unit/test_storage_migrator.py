"""Migrator unit tests. Avoid real filesystem SQL by writing .sql files into
``tmp_path / "migrations"`` and pointing the migrator at them directly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from startup_radar.storage.migrator import apply_pending


def _write(dir_: Path, name: str, body: str) -> None:
    (dir_ / name).write_text(body, encoding="utf-8")


def test_fresh_db_applies_all(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "0001_init.sql", "CREATE TABLE t (x INTEGER);")
    _write(migrations, "0002_add.sql", "ALTER TABLE t ADD COLUMN y INTEGER;")
    conn = sqlite3.connect(":memory:")

    applied = apply_pending(conn, migrations)

    assert applied == [1, 2]
    (v,) = conn.execute("PRAGMA user_version").fetchone()
    assert v == 2


def test_mid_version_applies_only_pending(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "0001_init.sql", "CREATE TABLE t (x INTEGER);")
    _write(migrations, "0002_add.sql", "ALTER TABLE t ADD COLUMN y INTEGER;")
    conn = sqlite3.connect(":memory:")
    conn.executescript("CREATE TABLE t (x INTEGER); PRAGMA user_version = 1;")

    applied = apply_pending(conn, migrations)

    assert applied == [2]


def test_idempotent(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "0001_init.sql", "CREATE TABLE t (x INTEGER);")
    conn = sqlite3.connect(":memory:")

    apply_pending(conn, migrations)
    assert apply_pending(conn, migrations) == []


def test_malformed_rolls_back(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "0001_good.sql", "CREATE TABLE a (x INTEGER);")
    _write(migrations, "0002_bad.sql", "CREATE TABLE b (x INTEGER); GARBAGE;")
    conn = sqlite3.connect(":memory:")

    with pytest.raises(sqlite3.Error):
        apply_pending(conn, migrations)

    (v,) = conn.execute("PRAGMA user_version").fetchone()
    assert v == 1


def test_filename_validation(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "001_short.sql", "CREATE TABLE t (x INTEGER);")
    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="bad migration filename"):
        apply_pending(conn, migrations)


def test_gap_rejected(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "0001_a.sql", "CREATE TABLE a (x INTEGER);")
    _write(migrations, "0003_c.sql", "CREATE TABLE c (x INTEGER);")
    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="expected migration 0002"):
        apply_pending(conn, migrations)


def test_initial_migration_is_idempotent_over_populated_db(tmp_path: Path) -> None:
    """Simulates a pre-Phase-10 DB (user_version=0, tables already exist).
    Every migration's CREATE is IF NOT EXISTS, so applying the full set over
    a populated DB is safe.
    """
    real_migrations = (
        Path(__file__).resolve().parents[2] / "startup_radar" / "storage" / "migrations"
    )
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE startups (
            id INTEGER PRIMARY KEY AUTOINCREMENT, company_name TEXT NOT NULL
        );
        """
    )
    applied = apply_pending(conn, real_migrations)
    assert applied == [1, 2]
    (v,) = conn.execute("PRAGMA user_version").fetchone()
    assert v == 2


def test_migrate_0001_to_0002_preserves_data(tmp_path: Path) -> None:
    """Seed startups at user_version=1, then apply 0002; data must survive."""
    real_migrations = (
        Path(__file__).resolve().parents[2] / "startup_radar" / "storage" / "migrations"
    )
    conn = sqlite3.connect(":memory:")
    # Apply 0001 only by pointing at a copy of just that file.
    stage = tmp_path / "m1_only"
    stage.mkdir()
    (stage / "0001_initial.sql").write_text(
        (real_migrations / "0001_initial.sql").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    apply_pending(conn, stage)
    conn.execute("INSERT INTO startups (company_name) VALUES ('Seeded Co')")
    conn.commit()

    applied = apply_pending(conn, real_migrations)
    assert applied == [2]
    (v,) = conn.execute("PRAGMA user_version").fetchone()
    assert v == 2
    (n,) = conn.execute("SELECT COUNT(*) FROM startups").fetchone()
    assert n == 1
    # runs table now exists and is empty
    (r,) = conn.execute("SELECT COUNT(*) FROM runs").fetchone()
    assert r == 0
