---
name: data-branch-restore
description: Pull the latest production SQLite DB from the orphan `data` branch into the local working tree, then run `startup-radar status` to confirm row counts.
when_to_use: When the user says "restore prod db", "pull the latest data", "/data-branch-restore", "sync down from the cloud", or after wiping `startup_radar.db` locally. NEVER auto-invoke.
allowed-tools: [Bash]
---

# /data-branch-restore — pull prod DB locally

Wraps the two-command restore from `docs/operations/data-branch.md`.

## Procedure

### 1. Warn if local DB has unsaved state

```bash
stat startup_radar.db 2>/dev/null && echo EXISTS || echo MISSING
```

If the local DB exists, warn the user we're about to overwrite it:

> A local `startup_radar.db` exists. Restoring will overwrite it with the latest from the `data` branch. Any changes only on this machine (e.g. application-tracking edits not yet picked up by the pipeline) will be lost. Proceed? (yes / cancel / backup-first)

If "backup-first", invoke `/backup` (with `--db-only` posture) before continuing.
If "cancel", STOP.

### 2. Fetch + checkout the file

```bash
git fetch origin data:data
git checkout data -- startup_radar.db
```

### 3. Verify

```bash
uv run startup-radar status
```

If row counts are non-zero, tell the user "restored; latest data is from <last-run-age>". If row counts are all zero, surface: "restored, but the prod DB on `data` branch appears empty — has the daily workflow run yet? Try `/data-branch-bootstrap` if this is a fresh fork, or check the GH Actions tab."

## Constraints

- Don't use `git fetch origin data` (without `data:data`) — that fetches the ref but doesn't create a local branch, and the next `git checkout data -- …` will fail.
- Don't `git checkout data` (no `--`). That would switch the working tree to the orphan branch (a destructive context switch). The `--` makes it a path-only restore.
- This skill does NOT need the `STARTUP_RADAR_DATA_BOOTSTRAP=1` handshake — it only fetches and checks out files; no push.
