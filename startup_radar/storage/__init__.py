"""Storage subpackage — single entry point for DB access."""

from __future__ import annotations

from pathlib import Path

from startup_radar.config import AppConfig
from startup_radar.storage.base import Storage
from startup_radar.storage.sqlite import SqliteStorage


def load_storage(cfg: AppConfig) -> Storage:
    """Instantiate the configured backend, run pending migrations, return."""
    if not cfg.output.sqlite.enabled:
        raise RuntimeError("sqlite output is disabled; no other backend configured")
    storage = SqliteStorage(Path(cfg.output.sqlite.path))
    storage.migrate_to_latest()
    return storage


__all__ = ["Storage", "SqliteStorage", "load_storage"]
