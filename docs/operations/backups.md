# Backups

Phase 6 shipped `startup-radar backup` — a local tarball of the DB, config, and OAuth credentials.

## Usage

```bash
uv run startup-radar backup                # DB + config.yaml + token.json + credentials.json
uv run startup-radar backup --no-secrets   # exclude token.json + credentials.json
uv run startup-radar backup --db-only      # only startup_radar.db (implies --no-secrets)
uv run startup-radar backup -o /path/to/tarball.tar.gz
```

Default destination is `backups/startup-radar-<YYYYmmdd-HHMMSS>.tar.gz`. The `backups/` directory is `.gitignore`d — tarballs never leave the repo.

## Contents

- `startup_radar.db` (resolved from `cfg.output.sqlite.path`, falls back to repo-root default if config is broken — so `--db-only` works even when config.yaml is what you're trying to recover).
- `config.yaml` (unless `--db-only`).
- `token.json`, `credentials.json` (unless `--no-secrets` or `--db-only`).

## Restore

Tarballs are gzipped tar. Restore manually:

```bash
tar -xzvf backups/startup-radar-<timestamp>.tar.gz -C <target-dir>
```

Then overlay the files back into your repo root.

For the production DB specifically, the [data branch restore](data-branch.md) is typically easier than restoring from a local backup.
