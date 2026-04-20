"""Startup Radar — Typer CLI. Single entry point for run / serve / deepdive."""

from __future__ import annotations

import functools
import io
import logging
import os
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, TypeVar

import typer

from startup_radar.errors import StartupRadarError

app = typer.Typer(
    name="startup-radar",
    help="Personal startup discovery radar — RSS/HN/EDGAR/Gmail → SQLite → Streamlit.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

_MAX_SCHEDULED_RUNTIME_SEC = 15 * 60
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

_F = TypeVar("_F", bound=Callable[..., None])


@dataclass
class CLIState:
    config_path: Path | None = None
    debug: bool = False


def _json_logs() -> bool:
    from startup_radar.config import secrets

    s = secrets()
    return s.log_json or s.ci


def _catch_errors(func: _F) -> _F:
    """Boundary wrapper: one-line error for StartupRadarError, traceback only with --debug.

    Generic ``Exception`` propagates untouched so bugs keep surfacing loudly, per
    ``.claude/rules/observability.md``. ``typer.Exit`` is a control-flow signal and
    is re-raised unchanged.
    """

    @functools.wraps(func)
    def wrapper(ctx: typer.Context, *args: object, **kwargs: object) -> None:
        from startup_radar.observability.logging import get_logger

        log = get_logger(func.__module__)
        try:
            func(ctx, *args, **kwargs)
        except typer.Exit:
            raise
        except StartupRadarError as e:
            debug = isinstance(ctx.obj, CLIState) and ctx.obj.debug
            log.error("cli.error", command=func.__name__, error=str(e), exc_info=debug)
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from e

    return wrapper  # type: ignore[return-value]


@app.callback()
def _main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config.yaml. Overrides package-relative default.",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            help="Show full tracebacks on error.",
        ),
    ] = False,
) -> None:
    """Configure structlog once per process."""
    from startup_radar.observability.logging import configure_logging

    configure_logging(json=_json_logs())
    ctx.obj = CLIState(config_path=config, debug=debug)


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


def pipeline(config_path: Path | None = None) -> int:
    """Run the discovery pipeline once. Public API — also called by the
    ``Run pipeline now`` button in ``startup_radar.web.app``.
    """
    from startup_radar.config import load_config
    from startup_radar.filters import StartupFilter
    from startup_radar.models import Startup
    from startup_radar.observability.logging import get_logger
    from startup_radar.parsing.normalize import dedup_key
    from startup_radar.sources.registry import SOURCES
    from startup_radar.storage import load_storage

    log = get_logger(__name__)

    print("=" * 60)
    print("Startup Radar")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    cfg = load_config(path=config_path)
    storage = load_storage(cfg)
    uv_at_run = storage.user_version()

    try:
        all_startups: list[Startup] = []
        for key, source in SOURCES.items():
            sub_cfg = getattr(cfg.sources, key, None)
            if sub_cfg is None or not getattr(sub_cfg, "enabled", False):
                continue
            print(f"\n[{source.name}] Fetching...")
            started_at = datetime.utcnow().isoformat()
            err_repr: str | None = None
            found: list[Startup] = []
            try:
                found = source.fetch(cfg, storage=storage)
            except Exception as e:
                err_repr = repr(e)
                log.exception("source.unhandled", source=source.name)
            finally:
                storage.record_run(
                    key,
                    started_at=started_at,
                    ended_at=datetime.utcnow().isoformat(),
                    items_fetched=len(found),
                    items_kept=len(found),
                    error=err_repr,
                    user_version_at_run=uv_at_run,
                )
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

        existing = storage.get_existing_companies()
        rejected = storage.get_rejected_companies()
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
            added = storage.insert_startups(fresh)
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
    finally:
        storage.close()


# --- commands --------------------------------------------------------------


def _config_path(ctx: typer.Context) -> Path | None:
    obj = ctx.obj
    return obj.config_path if isinstance(obj, CLIState) else None


@app.command()
@_catch_errors
def run(
    ctx: typer.Context,
    scheduled: Annotated[
        bool,
        typer.Option(
            "--scheduled",
            help="Log to logs/YYYY-MM-DD.log with a 15-min timeout (cron mode).",
        ),
    ] = False,
) -> None:
    """Run the discovery pipeline once."""
    cfg_path = _config_path(ctx)
    if not scheduled:
        raise typer.Exit(code=pipeline(config_path=cfg_path))

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
        rc = pipeline(config_path=cfg_path)
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
@_catch_errors
def serve(
    ctx: typer.Context,
    port: Annotated[int, typer.Option(help="Port the dashboard binds to.")] = 8501,
    address: Annotated[
        str,
        typer.Option(help="Address the dashboard binds to. Use 0.0.0.0 inside Docker."),
    ] = "localhost",
) -> None:
    """Open the Streamlit dashboard."""
    import subprocess

    repo_root = Path(__file__).resolve().parent.parent
    app_path = repo_root / "startup_radar" / "web" / "app.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(port),
        "--server.address",
        address,
    ]
    env = os.environ.copy()
    cfg_path = _config_path(ctx)
    if cfg_path is not None:
        env["STARTUP_RADAR_CONFIG_PATH"] = str(cfg_path)
    raise typer.Exit(code=subprocess.call(cmd, env=env))


@app.command()
@_catch_errors
def deepdive(
    ctx: typer.Context,
    company: Annotated[str, typer.Argument(help="Company name, e.g. 'Anthropic'.")],
) -> None:
    """Generate a one-page research brief (.docx) for COMPANY."""
    from startup_radar.research.deepdive import generate

    del ctx  # accepted only so @_catch_errors can read ctx.obj.debug
    path = generate(company)
    typer.echo(f"Report saved: {path}")


# --- resilience commands (Phase 6) ----------------------------------------


@app.command()
@_catch_errors
def backup(
    ctx: typer.Context,
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
    raise typer.Exit(
        code=_backup(
            output=output,
            no_secrets=no_secrets,
            db_only=db_only,
            config_path=_config_path(ctx),
        )
    )


@app.command()
@_catch_errors
def doctor(
    ctx: typer.Context,
    network: Annotated[
        bool,
        typer.Option("--network", help="Include HTTP healthchecks for enabled sources."),
    ] = False,
) -> None:
    """Validate environment, config, credentials, and source reachability."""
    raise typer.Exit(code=_doctor(network=network, config_path=_config_path(ctx)))


@app.command()
@_catch_errors
def status(ctx: typer.Context) -> None:
    """Print branch, version, last-run age, DB row counts. No network."""
    raise typer.Exit(code=_status(config_path=_config_path(ctx)))


# --- resilience helpers ---------------------------------------------------


def _backup(
    *, output: Path | None, no_secrets: bool, db_only: bool, config_path: Path | None = None
) -> int:
    import tarfile

    from startup_radar.config import load_config

    repo_root = _repo_root()

    # Prefer the live config's sqlite.path; fall back to the default if the
    # config itself is broken (so `backup --db-only` still works when config
    # is the very thing the user is trying to recover from).
    try:
        cfg = load_config(path=config_path)
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


def _doctor(*, network: bool, config_path: Path | None = None) -> int:
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
        cfg = load_config(path=config_path)
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
            _, streak = _source_health(cfg, key)
            if streak > 2:
                checks.append(("⚠", f"source.{key}.streak", f"{streak} consecutive failed runs"))

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


def _status(*, config_path: Path | None = None) -> int:
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
    cfg = None
    try:
        from startup_radar.config import load_config

        cfg = load_config(path=config_path)
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

    if cfg is not None:
        print()
        print("Per-source health:")
        for key in ("rss", "hackernews", "sec_edgar", "gmail"):
            sub = getattr(cfg.sources, key, None)
            if sub is None or not getattr(sub, "enabled", False):
                print(f"  – {key:<12} (disabled)")
                continue
            lr, streak = _source_health(cfg, key)
            age = _run_age(lr)
            if streak > 2:
                marker = "⚠"
            elif lr and lr.get("error") is None:
                marker = "✓"
            else:
                marker = "–"
            failures = f"{streak} failures" if streak else "0 failures"
            print(f"  {marker} {key:<12} last run {age}  |  {failures}")
    return 0


def _source_health(cfg: object, source_key: str) -> tuple[dict | None, int]:
    """Read last_run + failure_streak for a source. Swallows errors.

    Resolves the sqlite path against `_repo_root()` when relative, mirroring
    what `_status` does for the DB row counts. `load_storage` itself trusts
    the caller's CWD, which doesn't hold for CLI helpers invoked from tests
    (`fake_repo` monkeypatches `_repo_root`, not CWD).
    """
    from startup_radar.storage.sqlite import SqliteStorage

    try:
        db_path = Path(cfg.output.sqlite.path)  # type: ignore[attr-defined]
        if not db_path.is_absolute():
            db_path = _repo_root() / db_path
        storage = SqliteStorage(db_path)
        storage.migrate_to_latest()
    except Exception:
        return (None, 0)
    try:
        return (storage.last_run(source_key), storage.failure_streak(source_key))
    except Exception:
        return (None, 0)
    finally:
        try:
            storage.close()
        except Exception:
            pass


def _run_age(lr: dict | None) -> str:
    if not lr:
        return "never"
    end = lr.get("ended_at") or lr.get("started_at")
    if not end:
        return "unknown"
    try:
        dt = datetime.fromisoformat(end)
    except ValueError:
        return "unknown"
    age_s = datetime.utcnow().timestamp() - dt.timestamp()
    if age_s < 0:
        age_s = 0
    return _format_age(age_s)


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
