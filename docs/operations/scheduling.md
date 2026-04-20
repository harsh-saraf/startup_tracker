# Scheduling

Startup Radar is designed to run once a day. The canonical scheduled entry point is:

```bash
uv run startup-radar run --scheduled
```

`--scheduled` differs from a bare `run` in two ways:

- **Logging.** Output is redirected to `logs/YYYY-MM-DD.log` via a `TextIOBase` wrapper around the project logger.
- **Timeout.** A 15-minute `threading.Timer` kills the process via `os._exit(1)` if the pipeline hangs.

Templates for cron, launchd, and Windows Task Scheduler live in the [`scheduling/`](https://github.com/xavierahojjx-afk/startup-radar-template/tree/main/scheduling) directory at the repo root.

## GH Actions (recommended)

`.github/workflows/daily.yml` runs the pipeline on a cron schedule inside GitHub Actions and persists the resulting SQLite DB by committing it to the orphan [`data` branch](data-branch.md).

First-time setup: run `/data-branch-bootstrap` in Claude Code (or follow the manual bootstrap in [Data branch](data-branch.md)). After that the daily workflow is self-sustaining; a weekly GC workflow trims history.

## Local cron

```cron
0 9 * * *  cd /path/to/startup-radar-template && /path/to/uv run startup-radar run --scheduled
```

Logs land under `logs/`. The `status` command reports the age of the newest log as "Last run".

## launchd (macOS)

See `scheduling/com.startupradar.daily.plist.example` — copy to `~/Library/LaunchAgents/`, edit the `WorkingDirectory` and `ProgramArguments`, then `launchctl load` it.

## Windows Task Scheduler

See `scheduling/windows-task.xml.example` — import via `schtasks /create /xml …`.
