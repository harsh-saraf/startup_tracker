-- 0002_runs_table.sql — per-source run telemetry.
-- One row per (source, invocation) written by cli.pipeline() via
-- Storage.record_run(...). Queried by Storage.last_run / failure_streak.
-- Idempotent over pre-Phase-11 DBs via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    items_fetched INTEGER,
    items_kept INTEGER,
    error TEXT,
    user_version_at_run INTEGER
);

CREATE INDEX IF NOT EXISTS idx_runs_source_id
    ON runs(source, id DESC);
