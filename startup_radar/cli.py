"""Startup Radar — Typer CLI. Single entry point for run / serve / deepdive."""

from __future__ import annotations

import io
import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="startup-radar",
    help="Personal startup discovery radar — RSS/HN/EDGAR/Gmail → SQLite → Streamlit.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

_MAX_SCHEDULED_RUNTIME_SEC = 15 * 60
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def _repo_root() -> Path:
    """Repo root for resolving DB / config / logs. Tests monkeypatch this."""
    return Path(__file__).resolve().parent.parent


# --- shared helpers --------------------------------------------------------


def _setup_scheduled_logging() -> logging.Logger:
    _LOG_DIR.mkdir(exist_ok=True)
    log_file = _LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    logger = logging.getLogger("startup_radar")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


class _LogStream(io.TextIOBase):
    """Redirects print() output into the logger so the pipeline's step-by-step
    messages land in logs/YYYY-MM-DD.log. Temporary — Phase 13 replaces with structlog."""

    encoding = "utf-8"

    def __init__(self, log: logging.Logger):
        self._log = log

    def write(self, msg: str) -> int:
        for line in msg.rstrip().splitlines():
            stripped = line.strip()
            if stripped:
                self._log.info(stripped)
        return len(msg)

    def flush(self) -> None:
        pass


def pipeline() -> int:
    """Run the discovery pipeline once. Public API — also called by the
    ``Run pipeline now`` button in ``startup_radar.web.app``.
    """
    import database
    from startup_radar.config import load_config
    from startup_radar.filters import StartupFilter
    from startup_radar.models import Startup
    from startup_radar.parsing.normalize import dedup_key
    from startup_radar.sources.registry import SOURCES

    print("=" * 60)
    print("Startup Radar")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    cfg = load_config()
    sqlite_cfg = cfg.output.sqlite
    if sqlite_cfg.enabled and sqlite_cfg.path:
        database.set_db_path(sqlite_cfg.path)
    database.init_db()

    all_startups: list[Startup] = []
    for key, source in SOURCES.items():
        sub_cfg = getattr(cfg.sources, key, None)
        if sub_cfg is None or not getattr(sub_cfg, "enabled", False):
            continue
        print(f"\n[{source.name}] Fetching...")
        found = source.fetch(cfg)
        print(f"  {len(found)} candidate(s)")
        all_startups.extend(found)

    print(f"\nTotal extracted: {len(all_startups)}")
    filtered = StartupFilter(cfg).filter(all_startups)
    print(f"After filter: {len(filtered)}")

    seen: set[str] = set()
    deduped: list[Startup] = []
    for s in filtered:
        key = dedup_key(s.company_name)
        if key and key not in seen:
            seen.add(key)
            deduped.append(s)
    if len(deduped) < len(filtered):
        print(f"After dedup: {len(deduped)}")

    existing = database.get_existing_companies()
    rejected = database.get_rejected_companies()
    fresh = [
        s
        for s in deduped
        if s.company_name.lower().strip() not in existing
        and s.company_name.lower().strip() not in rejected
    ]
    skipped = len(deduped) - len(fresh)
    if skipped:
        print(f"Skipped {skipped} already-seen or rejected")

    if fresh:
        added = database.insert_startups(fresh)
        print(f"Added {added} new startup(s) to SQLite")
        for s in fresh:
            amount = f" | {s.amount_raised}" if s.amount_raised else ""
            stage = f" | {s.funding_stage}" if s.funding_stage else ""
            print(f"  {s.company_name}{stage}{amount}  [{s.source}]")
    else:
        print("No new startups to add")

    sheets_cfg = cfg.output.google_sheets
    if sheets_cfg.enabled and fresh:
        try:
            from sinks import google_sheets

            google_sheets.append_startups(sheets_cfg.sheet_id, fresh)
            print(f"Wrote {len(fresh)} to Google Sheet")
        except Exception as e:
            print(f"Google Sheets write failed: {e}")

    print("\nDone.")
    return 0


# --- commands --------------------------------------------------------------


@app.command()
def run(
    scheduled: Annotated[
        bool,
        typer.Option(
            "--scheduled",
            help="Log to logs/YYYY-MM-DD.log with a 15-min timeout (cron mode).",
        ),
    ] = False,
) -> None:
    """Run the discovery pipeline once."""
    if not scheduled:
        raise typer.Exit(code=pipeline())

    logger = _setup_scheduled_logging()
    logger.info("Startup Radar scheduled run starting")

    def _timeout() -> None:
        logger.error(f"Run timed out after {_MAX_SCHEDULED_RUNTIME_SEC // 60} minutes")
        os._exit(1)

    timer = threading.Timer(_MAX_SCHEDULED_RUNTIME_SEC, _timeout)
    timer.daemon = True
    timer.start()

    old_stdout = sys.stdout
    sys.stdout = _LogStream(logger)
    try:
        rc = pipeline()
        sys.stdout = old_stdout
        timer.cancel()
        logger.info("Scheduled run completed successfully")
        raise typer.Exit(code=rc)
    except typer.Exit:
        raise
    except Exception as e:
        sys.stdout = old_stdout
        timer.cancel()
        msg = str(e).lower()
        if "token" in msg or "credentials" in msg or "refresh" in msg:
            logger.error(f"OAuth token expired or invalid: {e}")
            logger.error("Delete token.json and run `startup-radar run` to re-authenticate.")
        else:
            logger.error(f"Scheduled run failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


@app.command()
def serve(
    port: Annotated[int, typer.Option(help="Port the dashboard binds to.")] = 8501,
) -> None:
    """Open the Streamlit dashboard."""
    import subprocess

    repo_root = Path(__file__).resolve().parent.parent
    app_path = repo_root / "startup_radar" / "web" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)]
    raise typer.Exit(code=subprocess.call(cmd))


@app.command()
def deepdive(
    company: Annotated[str, typer.Argument(help="Company name, e.g. 'Anthropic'.")],
) -> None:
    """Generate a one-page research brief (.docx) for COMPANY."""
    from startup_radar.research.deepdive import generate

    path = generate(company)
    typer.echo(f"Report saved: {path}")


# --- resilience commands (Phase 6) ----------------------------------------


@app.command()
def backup(
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Destination tarball. Default: backups/startup-radar-<ts>.tar.gz.",
        ),
    ] = None,
    no_secrets: Annotated[
        bool,
        typer.Option("--no-secrets", help="Exclude token.json and credentials.json."),
    ] = False,
    db_only: Annotated[
        bool,
        typer.Option(
            "--db-only",
            help="Pack startup_radar.db only. Implies --no-secrets and skips config.yaml.",
        ),
    ] = False,
) -> None:
    """Tar up DB + config + OAuth for local resilience."""
    raise typer.Exit(code=_backup(output=output, no_secrets=no_secrets, db_only=db_only))


@app.command()
def doctor(
    network: Annotated[
        bool,
        typer.Option("--network", help="Include HTTP healthchecks for enabled sources."),
    ] = False,
) -> None:
    """Validate environment, config, credentials, and source reachability."""
    raise typer.Exit(code=_doctor(network=network))


@app.command()
def status() -> None:
    """Print branch, version, last-run age, DB row counts. No network."""
    raise typer.Exit(code=_status())


# --- resilience helpers ---------------------------------------------------


def _backup(*, output: Path | None, no_secrets: bool, db_only: bool) -> int:
    import tarfile

    from startup_radar.config import load_config

    repo_root = _repo_root()

    # Prefer the live config's sqlite.path; fall back to the default if the
    # config itself is broken (so `backup --db-only` still works when config
    # is the very thing the user is trying to recover from).
    try:
        cfg = load_config()
        db_path = Path(cfg.output.sqlite.path)
        if not db_path.is_absolute():
            db_path = repo_root / db_path
    except Exception:
        db_path = repo_root / "startup_radar.db"

    if db_only and not db_path.exists():
        print(f"✗ DB not found at {db_path}")
        return 1

    items: list[tuple[Path, str]] = []
    if db_path.exists():
        items.append((db_path, db_path.name))
    if not db_only:
        cfg_file = repo_root / "config.yaml"
        if cfg_file.exists():
            items.append((cfg_file, "config.yaml"))
        if not no_secrets:
            for secret in ("token.json", "credentials.json"):
                p = repo_root / secret
                if p.exists():
                    items.append((p, secret))

    if not items:
        print("✗ Nothing to back up (no DB, no config, no secrets found).")
        return 1

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if output is None:
        backups_dir = repo_root / "backups"
        backups_dir.mkdir(exist_ok=True)
        output = backups_dir / f"startup-radar-{ts}.tar.gz"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(output, "w:gz") as tar:
        for src, arcname in items:
            tar.add(src, arcname=arcname)

    size_kb = output.stat().st_size / 1024
    manifest = ", ".join(a for _, a in items)
    print(f"✓ Backup written: {output}  ({size_kb:.1f} KB)")
    print(f"  Contents: {manifest}")
    return 0


def _doctor(*, network: bool) -> int:
    import shutil

    from startup_radar.config import ConfigError, load_config
    from startup_radar.sources.registry import SOURCES

    repo_root = _repo_root()
    checks: list[tuple[str, str, str]] = []  # (mark, title, detail)
    fails = 0

    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 10):
        checks.append(("✓", "Python version", f"{major}.{minor}"))
    else:
        checks.append(("✗", "Python version", f"{major}.{minor} (need ≥3.10)"))
        fails += 1

    cfg = None
    try:
        cfg = load_config()
        checks.append(("✓", "config.yaml", "validates against AppConfig schema"))
    except ConfigError as e:
        first = str(e).splitlines()[0]
        checks.append(("✗", "config.yaml", first))
        fails += 1

    if cfg is not None:
        db_path = Path(cfg.output.sqlite.path)
        if not db_path.is_absolute():
            db_path = repo_root / db_path
        db_dir = db_path.parent
        if os.access(db_dir, os.W_OK):
            checks.append(("✓", "SQLite path", f"{db_path} (parent writable)"))
        else:
            checks.append(("✗", "SQLite path", f"{db_dir} not writable"))
            fails += 1

    try:
        free_mb = shutil.disk_usage(repo_root).free // (1024 * 1024)
        if free_mb >= 100:
            checks.append(("✓", "Disk free", f"{free_mb} MB"))
        else:
            checks.append(("⚠", "Disk free", f"{free_mb} MB (low, but non-fatal)"))
    except OSError as e:
        checks.append(("⚠", "Disk free", f"unknown: {e}"))

    if cfg is not None:
        for key, source in SOURCES.items():
            sub = getattr(cfg.sources, key, None)
            if sub is None or not getattr(sub, "enabled", False):
                checks.append(("⚠", f"source.{key}", "disabled in config"))
                continue
            try:
                ok, detail = source.healthcheck(cfg, network=network)
                mark = "✓" if ok else "✗"
                checks.append((mark, f"source.{key}", detail))
                if not ok:
                    fails += 1
            except Exception as e:
                checks.append(("✗", f"source.{key}", f"healthcheck raised: {e}"))
                fails += 1

    print("=" * 60)
    print(f"Startup Radar — doctor  ({'network' if network else 'fast'} mode)")
    print("=" * 60)
    for mark, title, detail in checks:
        print(f"  {mark} {title:<24} {detail}")
    print()
    if fails:
        print(f"✗ {fails} check(s) failed.")
    else:
        print("✓ All checks passed.")
    return 1 if fails else 0


def _status() -> int:
    import sqlite3
    import subprocess

    repo_root = _repo_root()

    try:
        from startup_radar import __version__

        version = __version__
    except ImportError:
        version = "unknown"

    try:
        branch = (
            subprocess.check_output(
                ["git", "branch", "--show-current"],
                cwd=repo_root,
                text=True,
                timeout=2,
            ).strip()
            or "(detached)"
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        branch = "(not a git repo)"

    logs_dir = repo_root / "logs"
    latest_log: Path | None = None
    last_run_age = "never"
    if logs_dir.is_dir():
        log_files = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if log_files:
            latest_log = log_files[0]
            age_s = datetime.now().timestamp() - latest_log.stat().st_mtime
            last_run_age = _format_age(age_s)

    db_counts: dict[str, int | str] = {"startups": 0, "job_matches": 0, "connections": 0}
    db_size = "—"
    try:
        from startup_radar.config import load_config

        cfg = load_config()
        db_path = Path(cfg.output.sqlite.path)
        if not db_path.is_absolute():
            db_path = repo_root / db_path
        if db_path.exists():
            db_size = f"{db_path.stat().st_size / 1024:.1f} KB"
            with sqlite3.connect(str(db_path)) as conn:
                for table in db_counts:
                    try:
                        (n,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                        db_counts[table] = n
                    except sqlite3.OperationalError:
                        db_counts[table] = "—"
    except Exception as e:
        db_counts = {"startups": f"error: {e}", "job_matches": "—", "connections": "—"}

    print(f"Branch:         {branch}")
    print(f"Version:        {version}")
    print(f"Last run:       {last_run_age}" + (f"  ({latest_log.name})" if latest_log else ""))
    print(f"DB size:        {db_size}")
    print(
        f"DB rows:        startups={db_counts['startups']}  "
        f"job_matches={db_counts['job_matches']}  connections={db_counts['connections']}"
    )
    return 0


def _format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


if __name__ == "__main__":
    app()
