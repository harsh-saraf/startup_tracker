# Operations

Day-to-day operational docs for running Startup Radar.

- **[Data branch](data-branch.md)** — the orphan `data` branch that holds the production SQLite DB between GH Actions runs. Includes the one-time bootstrap (or run the `/data-branch-bootstrap` skill) and the `git fetch origin data:data && git checkout data -- startup_radar.db` restore.
- **[Backups](backups.md)** — local tarballs via `uv run startup-radar backup [--no-secrets] [--db-only]`.
- **[Scheduling](scheduling.md)** — cron, launchd, Windows Task Scheduler, and the daily GH Actions workflow.
