"""Shared pytest fixtures for Phase 6 CLI tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Tmp_path with a minimal (config.yaml, startup_radar.db, logs/) layout.

    Monkeypatches both `startup_radar.cli._repo_root` and the loader's
    `CONFIG_FILE` constant so all three Phase-6 helpers consistently see
    the tmp_path, not the real repo.
    """
    example = REPO_ROOT / "config.example.yaml"
    (tmp_path / "config.yaml").write_text(example.read_text(encoding="utf-8"))

    db = tmp_path / "startup_radar.db"
    with sqlite3.connect(str(db)) as conn:
        conn.executescript(
            """
            CREATE TABLE startups (id INTEGER PRIMARY KEY, company_name TEXT);
            CREATE TABLE job_matches (id INTEGER PRIMARY KEY, company_name TEXT);
            CREATE TABLE connections (id INTEGER PRIMARY KEY, company TEXT);
            """
        )

    (tmp_path / "logs").mkdir()

    monkeypatch.setattr("startup_radar.cli._repo_root", lambda: tmp_path)
    monkeypatch.setattr("startup_radar.config.loader.CONFIG_FILE", tmp_path / "config.yaml")
    return tmp_path
