# Phase 6 Execution Plan — Resilience CLI (`backup`, `doctor`, `status`)

> Add three resilience commands to the Typer CLI: `backup` (tarball of DB + config + OAuth), `doctor` (validates env + config + per-source healthchecks, exit 0/1), `status` (last-run age + DB row counts). Extends the `Source.healthcheck()` default to a typed `(ok, detail)` contract and overrides it per source. No schema/storage changes. No new runtime deps.

## Phase summary

- **`startup-radar backup`** — writes `backups/startup-radar-YYYYMMDD-HHMMSS.tar.gz` containing `startup_radar.db`, `config.yaml`, `token.json`, `credentials.json`. Flags: `--output/-o PATH`, `--no-secrets` (skips `token.json`/`credentials.json`), `--db-only`. Missing source files are skipped with a note, never a crash. Stdout: single line with archive path + byte size. Exit 0 on any archive written; exit 1 if DB itself missing and `--db-only` set.
- **`startup-radar doctor`** — runs 6 check categories, prints a `✓ / ✗ / ⚠` report, exits 0 if zero failures (warnings OK), else 1. Categories: python-version, config-validates, db-writable, disk-free, credentials-present (per enabled source), source-healthcheck (per enabled source). `--network` flag (default `false`) gates the HTTP-touching source healthchecks; default is filesystem/config-only so CI can run it fast.
- **`startup-radar status`** — prints current branch, version (from `startup_radar.__version__`), last-run age (mtime of newest `logs/*.log`), DB row counts (`startups`, `job_matches`, `connections`), total DB size on disk. No network calls. Pure read. Exit 0.
- **Extend `Source.healthcheck()`** signature: `healthcheck(cfg: AppConfig, *, network: bool = False) -> tuple[bool, str]`. Default impl returns `(True, "no healthcheck defined")`. Each of the 4 sources overrides:
  - `rss`: fast → check `cfg.sources.rss.feeds` is non-empty. network → HEAD first feed URL, 10 s timeout.
  - `hackernews`: fast → check `cfg.sources.hackernews.queries` is non-empty. network → HEAD `https://hn.algolia.com/api/v1/search?query=test` with 10 s timeout.
  - `sec_edgar`: fast → check `cfg.sources.sec_edgar.industry_sic_codes` non-empty. network → HEAD EDGAR browse endpoint with UA header.
  - `gmail`: fast → check `token.json` + `credentials.json` both exist. network → same (no API call — OAuth refresh happens implicitly during `run`; Phase 6 doesn't pre-emptively refresh).
- **`.gitignore`** — add `backups/` (directory) and `*.tar.gz` (safety net).
- **Tests** — `tests/test_cli_backup.py`, `tests/test_cli_doctor.py`, `tests/test_cli_status.py` using Typer's `CliRunner`. Each Phase-6 command gets ≥3 tests against a `tmp_path`-scoped fake repo. Total new tests: ~12.
- **Docs / harness** — update `.claude/CLAUDE.md` (layout note, new commands in the quickref table), `.claude/rules/sources.md` (new `healthcheck()` signature), `.claude/settings.json` (allowlist `Bash(uv run startup-radar backup *)` etc.), `AGENTS.md`, `README.md`, `docs/AUDIT_FINDINGS.md`, `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 8.

## Out of scope (deferred)

| Item | Deferred to | Why |
|---|---|---|
| Restore command (`backup restore`) | Phase 12 | Restore is coupled to schema versioning — replacing a `*.db` without a `PRAGMA user_version` check can yield a silently-broken dashboard. Phase 12 pairs restore with the migrator. |
| Cloud sync for backups (S3, rclone, Turso) | Phase 9 | Phase 9 rebuilds GH-Actions DB persistence; if cloud sync lands it lands there. Local tarball is sufficient for the single-user local case Phase 6 targets. |
| Per-source failure counters / `runs` table | Phase 13 | Requires a schema change + structlog. Phase 6 `status` reads logs' mtime only; no aggregate counter surface. Dashboard "System Health" page (§4.3) also defers. |
| Auto-rotation of old backups (`--keep N`) | Phase 9 | Premature — user can `ls backups/ | tail -n +N | xargs rm`. Add if backups become a disk-space footgun. |
| Gmail token auto-refresh inside `doctor` | Phase 13 | Pairs with `secrets.py` + structlog. `doctor` today only reports missing/expired; user re-runs `run` to refresh. (Same as `daily_run.py:88-90` behavior.) |
| Per-source healthcheck timeouts as config | Phase 13 | Shared `httpx.Client` with timeouts lands Phase 13. Phase 6 hardcodes `timeout=10` for all network probes. |
| `doctor --format=json` | Phase 13 | No current JSON consumer. Human output only. |
| `doctor` as automatic pre-flight for `run` / `serve` | Phase 8 wizard | The wizard owns the "green first run" flow. `run` today just attempts and surfaces real errors — explicit pre-flight is friction. |
| `status --json` or dashboard widget | Phase 11 | Dashboard decomposition phase owns surfacing. `status` is CLI-only in Phase 6. |
| Encrypt backup tarballs | never | Backups live on the user's own disk; they already hold `token.json`. Encryption would require key management for a single-user tool — out of scope per `docs/CRITIQUE_APPENDIX.md` §12. |

## Effort estimate

- 0.5 engineering day per the reordered execution in `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 8.
- Critical path: `Source.healthcheck` signature change (breaks the ABC contract). All 4 sources get overrides in the same diff.
- Secondary path: Typer `CliRunner` testing fan-out — each of 3 commands needs a tmp_path fixture that fakes the full `startup_radar.db` + `config.yaml` + `logs/` layout. One shared conftest fixture reduces repetition.
- Tag at end as `phase-6`.

## Prerequisites

- ✅ Phase 5: pydantic AppConfig + filters move (commit `db8d99b`, tag `phase-5`).
- ✅ `make ci` green at start.
- ✅ Working tree clean.
- No new runtime deps. `tarfile` + `shutil.disk_usage` are stdlib. Typer + `requests` already in.

---

## 1. Files to change

| Path | Action | Notes |
|---|---|---|
| `startup_radar/cli.py` | edit | Add `backup`, `doctor`, `status` commands + private helpers `_backup`, `_doctor`, `_status`. Wire `print()` for user-visible output per observability rule. ~180 lines added. |
| `startup_radar/sources/base.py` | edit | Change `healthcheck()` signature: `healthcheck(self, cfg: AppConfig, *, network: bool = False) -> tuple[bool, str]`. Default returns `(True, "no healthcheck defined")`. |
| `startup_radar/sources/rss.py` | edit | Override `healthcheck()` per §2.4. |
| `startup_radar/sources/hackernews.py` | edit | Override `healthcheck()` per §2.4. |
| `startup_radar/sources/sec_edgar.py` | edit | Override `healthcheck()` per §2.4. |
| `startup_radar/sources/gmail.py` | edit | Override `healthcheck()` per §2.4 — filesystem-only (no network probe even under `--network`). |
| `.gitignore` | edit | Add `backups/` and `*.tar.gz`. |
| `pyproject.toml` | edit | No new deps. Ensure `startup_radar/cli.py` stays outside `[tool.mypy] files` (transitive `requests`/`streamlit` stub noise per Phase 4 rationale). New test files auto-picked-up by pytest discovery. |
| `tests/test_cli_backup.py` | **create** | ~80 lines. See §2.5. |
| `tests/test_cli_doctor.py` | **create** | ~120 lines. See §2.6. |
| `tests/test_cli_status.py` | **create** | ~80 lines. See §2.7. |
| `tests/conftest.py` | **create** | Shared `fake_repo` fixture — tmp_path with `config.yaml` (copied from `config.example.yaml`), empty `startup_radar.db`, empty `logs/`. ~40 lines. |
| `.claude/CLAUDE.md` | edit | Repo-layout table: add a row for `backups/`. Common-commands block: add `backup`, `doctor`, `status` rows. Invariants: none new. |
| `.claude/rules/sources.md` | edit | Update `healthcheck()` signature note; clarify fast vs. network modes. |
| `.claude/settings.json` | edit | Allow `Bash(uv run startup-radar backup *)`, `Bash(uv run startup-radar doctor *)`, `Bash(uv run startup-radar status *)`. Deny `Edit(backups/**)` (belt-and-braces — backup tarballs shouldn't be edited). |
| `.claude/hooks/pre-commit-check.sh` | edit | Add a guard: refuse to commit any `backups/*` path. |
| `AGENTS.md` | edit | Commands section adds `backup`, `doctor`, `status`. |
| `README.md` | edit | Usage section adds the three commands with one-line descriptions. Add a "resilience" note pointing at `backup`. |
| `docs/AUDIT_FINDINGS.md` | edit | New §N "Resilience" → RESOLVED (Phase 6) for the local-tarball-backup item; cloud-sync item remains open for Phase 9. |
| `docs/PRODUCTION_REFACTOR_PLAN.md` | edit | §0a row 8 → ✅ done. §0a "Adds" table row for `backup` → ✅ done. |
| `docs/plans/phase-6.md` | **create** | This document. |

### Files explicitly NOT to touch

- `database.py`, `connections.py`, `app.py` — `status` reads DB via `sqlite3` directly inside `cli.py` (three `SELECT COUNT(*)` queries); adding helpers to `database.py` is Phase 12's storage refactor.
- `startup_radar/parsing/**`, `startup_radar/research/deepdive.py`, `startup_radar/filters.py` — no coupling to this phase.
- `startup_radar/config/**` — schema stays as-is; Phase 6 consumes, doesn't extend.
- `config.yaml`, `config.example.yaml` — no shape changes.
- `.github/workflows/daily.yml` — unchanged. `doctor` is not wired into the workflow yet (Phase 9 rewrite).
- `sinks/google_sheets.py` — no healthcheck needed (it's a sink, not a source).
- `scheduling/*` templates — unchanged.

---

## 2. New/changed file shapes

### 2.1 `startup_radar/cli.py::backup` (new command)

```python
@app.command()
def backup(
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Destination tarball. Default: backups/startup-radar-<ts>.tar.gz."),
    ] = None,
    no_secrets: Annotated[
        bool,
        typer.Option("--no-secrets", help="Exclude token.json and credentials.json."),
    ] = False,
    db_only: Annotated[
        bool,
        typer.Option("--db-only", help="Pack startup_radar.db only. Implies --no-secrets and skips config.yaml."),
    ] = False,
) -> None:
    """Tar up DB + config + OAuth for local resilience."""
    raise typer.Exit(code=_backup(output=output, no_secrets=no_secrets, db_only=db_only))
```

Helper (~60 lines):

```python
def _backup(*, output: Path | None, no_secrets: bool, db_only: bool) -> int:
    import tarfile
    from startup_radar.config import load_config

    repo_root = _repo_root()

    # Determine DB path: prefer live config's sqlite.path if present, else default.
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

    items: list[tuple[Path, str]] = []   # (src, arcname)
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
```

Notes:
- No tarfile-slip risk — we supply `arcname` explicitly for each member (not a user-controlled path).
- `output.parent.mkdir(parents=True, exist_ok=True)` only fires when `-o` is given; defaults target `backups/` which we create ourselves.
- Default `backups/` dir is gitignored.

### 2.2 `startup_radar/cli.py::doctor`

```python
@app.command()
def doctor(
    network: Annotated[
        bool,
        typer.Option("--network", help="Include HTTP healthchecks for enabled sources."),
    ] = False,
) -> None:
    """Validate environment, config, credentials, and source reachability."""
    raise typer.Exit(code=_doctor(network=network))
```

Helper (~90 lines):

```python
def _doctor(*, network: bool) -> int:
    import shutil
    import sys as _sys

    from startup_radar.config import ConfigError, load_config
    from startup_radar.sources.registry import SOURCES

    repo_root = _repo_root()
    checks: list[tuple[str, str, str]] = []   # (status, title, detail); status in {"✓", "✗", "⚠"}
    fails = 0

    # 1. Python version
    major, minor = _sys.version_info[:2]
    if (major, minor) >= (3, 10):
        checks.append(("✓", "Python version", f"{major}.{minor}"))
    else:
        checks.append(("✗", "Python version", f"{major}.{minor} (need ≥3.10)"))
        fails += 1

    # 2. Config validates
    cfg = None
    try:
        cfg = load_config()
        checks.append(("✓", "config.yaml", "validates against AppConfig schema"))
    except ConfigError as e:
        first = str(e).splitlines()[0]
        checks.append(("✗", "config.yaml", first))
        fails += 1

    # 3. DB writable
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

    # 4. Disk free
    try:
        free_mb = shutil.disk_usage(repo_root).free // (1024 * 1024)
        if free_mb >= 100:
            checks.append(("✓", "Disk free", f"{free_mb} MB"))
        else:
            checks.append(("⚠", "Disk free", f"{free_mb} MB (low, but non-fatal)"))
    except OSError as e:
        checks.append(("⚠", "Disk free", f"unknown: {e}"))

    # 5 + 6. Per-source: credentials + healthcheck
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

    # Render
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
```

### 2.3 `startup_radar/cli.py::status`

```python
@app.command()
def status() -> None:
    """Print branch, version, last-run age, DB row counts. No network."""
    raise typer.Exit(code=_status())
```

Helper (~50 lines):

```python
def _status() -> int:
    import sqlite3
    import subprocess

    repo_root = _repo_root()

    try:
        from startup_radar import __version__
    except ImportError:
        __version__ = "unknown"

    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=repo_root, text=True, timeout=2
        ).strip() or "(detached)"
    except (subprocess.SubprocessError, FileNotFoundError):
        branch = "(not a git repo)"

    logs_dir = repo_root / "logs"
    latest_log = None
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
    print(f"Version:        {__version__}")
    print(f"Last run:       {last_run_age}" + (f"  ({latest_log.name})" if latest_log else ""))
    print(f"DB size:        {db_size}")
    print(f"DB rows:        startups={db_counts['startups']}  "
          f"job_matches={db_counts['job_matches']}  connections={db_counts['connections']}")
    return 0


def _format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"
```

### 2.4 Source `healthcheck` overrides

**`startup_radar/sources/base.py` diff:**

```diff
-    def healthcheck(self) -> bool:
-        return True
+    def healthcheck(self, cfg: AppConfig, *, network: bool = False) -> tuple[bool, str]:
+        """Return (ok, detail). `network=False` → filesystem/config checks only.
+        Override per source. Default implementation always returns (True, ...)."""
+        return (True, "no healthcheck defined")
```

**`startup_radar/sources/rss.py` (new method):**

```python
def healthcheck(self, cfg: AppConfig, *, network: bool = False) -> tuple[bool, str]:
    feeds = cfg.sources.rss.feeds
    if not feeds:
        return (False, "no feeds configured")
    if not network:
        return (True, f"{len(feeds)} feed(s) configured")
    import requests

    url = str(feeds[0].url)
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        if r.status_code < 400:
            return (True, f"{len(feeds)} feed(s); first feed HTTP {r.status_code}")
        return (False, f"first feed HTTP {r.status_code}")
    except requests.RequestException as e:
        return (False, f"first feed unreachable: {e.__class__.__name__}")
```

**`startup_radar/sources/hackernews.py` (new method):**

```python
def healthcheck(self, cfg: AppConfig, *, network: bool = False) -> tuple[bool, str]:
    queries = cfg.sources.hackernews.queries
    if not queries:
        return (False, "no queries configured")
    if not network:
        return (True, f"{len(queries)} quer(y|ies) configured")
    import requests

    try:
        r = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": "startup", "hitsPerPage": "1"},
            timeout=10,
        )
        if r.status_code == 200:
            return (True, f"Algolia API HTTP 200")
        return (False, f"Algolia API HTTP {r.status_code}")
    except requests.RequestException as e:
        return (False, f"Algolia unreachable: {e.__class__.__name__}")
```

**`startup_radar/sources/sec_edgar.py` (new method + extract module constant):**

Refactor the existing inline `"User-Agent": "startup-radar-template (...)"` string at `sec_edgar.py:24` into a module-level `_USER_AGENT` constant, then use it in both `fetch()` (existing call site) and the new `healthcheck()`:

```python
_USER_AGENT = "startup-radar-template (github.com/xavierahojjx-afk/startup-radar-template)"

# existing fetch(): headers={"User-Agent": _USER_AGENT, ...}

def healthcheck(self, cfg: AppConfig, *, network: bool = False) -> tuple[bool, str]:
    sic = cfg.sources.sec_edgar.industry_sic_codes
    if not sic:
        return (False, "no industry_sic_codes configured")
    if not network:
        return (True, f"{len(sic)} SIC code(s) configured")
    import requests

    try:
        r = requests.head(
            "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent",
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
            allow_redirects=True,
        )
        if r.status_code < 400:
            return (True, f"EDGAR HTTP {r.status_code}")
        return (False, f"EDGAR HTTP {r.status_code}")
    except requests.RequestException as e:
        return (False, f"EDGAR unreachable: {e.__class__.__name__}")
```

> The fetch-site edit is one-line; the constant is 1 line. No behavior change to `fetch()`.

**`startup_radar/sources/gmail.py` (new method):**

```python
def healthcheck(self, cfg: AppConfig, *, network: bool = False) -> tuple[bool, str]:
    repo_root = Path(__file__).resolve().parents[2]
    creds = repo_root / "credentials.json"
    token = repo_root / "token.json"
    if not creds.exists():
        return (False, "credentials.json missing")
    if not token.exists():
        return (False, "token.json missing — run `startup-radar run` once to auth")
    # Phase 6 does not proactively test-refresh the token — Phase 13.
    return (True, "credentials + token present")
```

### 2.5 `tests/test_cli_backup.py`

```python
"""Tests for `startup-radar backup`. Uses Typer's CliRunner against a tmp_path repo."""
from __future__ import annotations

import tarfile
from pathlib import Path

from typer.testing import CliRunner

from startup_radar.cli import app

runner = CliRunner()


def test_backup_default_writes_tarball(fake_repo: Path) -> None:
    """Default path: `backup` writes into backups/ under the (monkeypatched) repo root."""
    result = runner.invoke(app, ["backup", "--no-secrets"])
    assert result.exit_code == 0, result.output
    tarballs = list((fake_repo / "backups").glob("startup-radar-*.tar.gz"))
    assert len(tarballs) == 1
    with tarfile.open(tarballs[0]) as tar:
        names = set(tar.getnames())
    assert "startup_radar.db" in names
    assert "config.yaml" in names
    assert "token.json" not in names


def test_backup_db_only(fake_repo: Path) -> None:
    out = fake_repo / "custom" / "db.tar.gz"
    result = runner.invoke(app, ["backup", "-o", str(out), "--db-only"])
    assert result.exit_code == 0
    with tarfile.open(out) as tar:
        names = set(tar.getnames())
    assert names == {"startup_radar.db"}


def test_backup_db_only_missing_db_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the fake_repo fixture there's no DB — --db-only should exit 1."""
    monkeypatch.setattr("startup_radar.cli._repo_root", lambda: tmp_path)
    out = tmp_path / "backups" / "x.tar.gz"
    result = runner.invoke(app, ["backup", "-o", str(out), "--db-only"])
    assert result.exit_code == 1
    assert "DB not found" in result.output or "Nothing to back up" in result.output
```

### 2.6 `tests/test_cli_doctor.py`

```python
"""Tests for `startup-radar doctor`. Fast mode only — no network."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from startup_radar.cli import app

runner = CliRunner()


def test_doctor_fast_green(fake_repo: Path) -> None:
    result = runner.invoke(app, ["doctor"])
    # Exit may be 0 or 1 depending on fake_repo source config; at minimum
    # the header should render and Python-version row should be ✓.
    assert "doctor" in result.output
    assert "Python version" in result.output
    assert "✓ Python version" in result.output


def test_doctor_missing_config_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("startup_radar.cli._repo_root", lambda: tmp_path)
    monkeypatch.setattr("startup_radar.config.loader.CONFIG_FILE", tmp_path / "config.yaml")
    monkeypatch.setattr("startup_radar.config.loader.EXAMPLE_FILE", tmp_path / "config.example.yaml")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "config.yaml" in result.output


def test_doctor_fast_does_not_hit_network(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure default `doctor` invocation makes no HTTP calls."""
    def _fake(*a, **kw):
        raise AssertionError("network called in fast mode")

    monkeypatch.setattr("requests.head", _fake)
    monkeypatch.setattr("requests.get", _fake)

    runner.invoke(app, ["doctor"])  # must not raise


def test_doctor_network_invokes_healthcheck(fake_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--network flag triggers per-source healthchecks with network=True."""
    seen: list[bool] = []
    from startup_radar.sources.registry import SOURCES

    for src in SOURCES.values():
        original = src.healthcheck
        def _wrap(cfg, *, network=False, _orig=original):
            seen.append(network)
            return _orig(cfg, network=network)
        monkeypatch.setattr(src, "healthcheck", _wrap)

    runner.invoke(app, ["doctor", "--network"])
    assert any(seen), "no healthchecks invoked"
    assert all(seen), "at least one healthcheck ran with network=False"
```

### 2.7 `tests/test_cli_status.py`

```python
"""Tests for `startup-radar status`. Pure read, no network."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from startup_radar.cli import app

runner = CliRunner()


def test_status_reports_zero_rows_on_fresh_db(fake_repo: Path) -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "DB rows:" in result.output
    assert "startups=0" in result.output


def test_status_reports_nonzero_after_insert(fake_repo: Path) -> None:
    db = fake_repo / "startup_radar.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("INSERT INTO startups (company_name) VALUES ('X'), ('Y')")
    result = runner.invoke(app, ["status"])
    assert "startups=2" in result.output


def test_status_last_run_age(fake_repo: Path) -> None:
    logs = fake_repo / "logs"
    (logs / "2026-04-19.log").write_text("run log")
    result = runner.invoke(app, ["status"])
    assert "Last run:" in result.output
    assert "ago" in result.output
```

### 2.8 `tests/conftest.py`

```python
"""Shared pytest fixtures for Phase 6 CLI tests."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tmp_path with a minimal (config.yaml, startup_radar.db, logs/) layout.

    Monkeypatches both `startup_radar.cli._repo_root` and the loader's
    `CONFIG_FILE` constant so all three Phase-6 helpers consistently see
    the tmp_path, not the real repo.
    """
    example = REPO_ROOT / "config.example.yaml"
    cfg_text = example.read_text(encoding="utf-8")
    (tmp_path / "config.yaml").write_text(cfg_text)

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
```

> Note: `cli._backup` / `cli._doctor` / `cli._status` resolve `repo_root` via `Path(__file__).resolve().parent.parent` which points at the real repo, NOT the fake one. Extract a `_repo_root()` helper in `cli.py` purely for test-seams — monkeypatched in tests, never overridden at runtime. Deliberately NO env-var lookup here to preserve the `.claude/CLAUDE.md` invariant ("Never `os.getenv()` outside `startup_radar/config/`"). Add to `cli.py`:

```python
def _repo_root() -> Path:
    """Repo root for resolving DB / config / logs. Tests monkeypatch this."""
    return Path(__file__).resolve().parent.parent
```

The `fake_repo` fixture (§2.8) monkeypatches both `startup_radar.cli._repo_root` and `startup_radar.config.loader.CONFIG_FILE` so all three helpers consistently see the tmp_path. No production env-var surface.

### 2.9 `.gitignore` diff

```diff
+# Phase 6 backups
+backups/
+*.tar.gz
```

### 2.10 `.claude/CLAUDE.md` — Common commands diff

```diff
 ## Common commands
 ```bash
 make lint                        # ruff check
 make format                      # ruff format (writes)
 make format-check                # ruff format --check (no writes)
 make test                        # pytest
 make typecheck                   # mypy
 make ci                          # lint + format-check + typecheck + test
 make serve                       # uv run startup-radar serve
 make run                         # uv run startup-radar run
 uv run startup-radar run --scheduled      # cron/launchd mode (logs + 15-min timeout)
 uv run startup-radar deepdive "Anthropic" # research brief .docx
+uv run startup-radar status               # branch + version + last-run age + DB row counts
+uv run startup-radar doctor [--network]   # env / config / credentials / source healthchecks
+uv run startup-radar backup [--no-secrets] [--db-only] # local tar.gz of DB + config + OAuth
 ```
```

---

## 3. Step-by-step execution

### 3.1 Pre-flight

```bash
git status                               # clean
git log -1 --format='%h %s'              # db8d99b feat(config):...
git tag --list 'phase-*'                 # phase-0..5
make ci                                  # green
```

### 3.2 Extract `_repo_root` helper + extend `healthcheck` ABC

Single edit to `startup_radar/cli.py` to add the `_repo_root()` helper (no env-var; monkeypatched in tests).
Single edit to `startup_radar/sources/base.py` to change `healthcheck()` signature.

### 3.3 Override `healthcheck` in each source

Parallel `Edit` calls (four independent files):
- `startup_radar/sources/rss.py`
- `startup_radar/sources/hackernews.py`
- `startup_radar/sources/sec_edgar.py`
- `startup_radar/sources/gmail.py`

Smoke:
```bash
uv run python -c "
from startup_radar.config import load_config
from startup_radar.sources.registry import SOURCES
cfg = load_config()
for k, s in SOURCES.items():
    print(k, s.healthcheck(cfg))
"
```

### 3.4 Add `backup` / `doctor` / `status` commands

Single edit to `startup_radar/cli.py`:
- Add three `@app.command()` functions per §2.1–2.3.
- Add helpers `_backup`, `_doctor`, `_status`, `_format_age`, `_repo_root`.

Smoke:
```bash
uv run startup-radar --help        # three new commands listed
uv run startup-radar status
uv run startup-radar doctor
uv run startup-radar backup --db-only
ls backups/
```

### 3.5 Add `.gitignore` entries

```bash
# Edit .gitignore per §2.9
git check-ignore -v backups/ *.tar.gz   # both ignored
```

### 3.6 Add tests + shared fixture

Parallel `Write` calls:
- `tests/conftest.py` (§2.8)
- `tests/test_cli_backup.py` (§2.5)
- `tests/test_cli_doctor.py` (§2.6)
- `tests/test_cli_status.py` (§2.7)

Smoke:
```bash
uv run pytest tests/test_cli_backup.py tests/test_cli_doctor.py tests/test_cli_status.py -xvs
```

### 3.7 Re-sync entry points

```bash
uv sync --all-extras            # refresh `startup-radar` script wrapper for new subcommands
uv run startup-radar --help     # confirm three new commands appear
```

### 3.8 Full local CI

```bash
make ci
# Expected test count: 16 (Phase 5 baseline) + 12 (Phase 6) ≈ 28+
```

Any red: STOP. See §5 risks.

### 3.9 Update harness + docs

Parallel `Edit` calls per §1:
- `.claude/CLAUDE.md`, `.claude/rules/sources.md`, `.claude/settings.json`, `.claude/hooks/pre-commit-check.sh`
- `AGENTS.md`, `README.md`
- `docs/AUDIT_FINDINGS.md` (new §N Resilience → RESOLVED Phase 6, cloud-sync open for Phase 9)
- `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 8 → ✅ done; §0a Adds table `backup` row → ✅

### 3.10 Ship

Use `/ship`. Suggested commit message:

```
feat(cli): add backup, doctor, status resilience commands

Adds three Typer commands for local resilience:

- backup  — tars startup_radar.db + config.yaml + token.json +
  credentials.json into backups/startup-radar-<ts>.tar.gz. Flags:
  --output, --no-secrets, --db-only. Missing files skipped with a
  note (never crash). backups/ gitignored.

- doctor  — runs 6 categories of checks (python version, config
  schema, DB path writable, disk free, per-source credentials,
  per-source healthcheck), exits 0 green / 1 red / warnings
  non-fatal. --network flag gates HTTP probes; default is
  filesystem-only so CI can run it fast.

- status  — prints branch, version, last-run age (from logs/*.log
  mtime), DB row counts (startups/job_matches/connections), DB
  size. No network. No writes.

Extends Source.healthcheck() to (cfg, *, network=False) ->
tuple[bool, str]; all four sources override it. Default ABC impl
returns (True, "no healthcheck defined") — backward-compatible
for any future source added before Phase 13.

Adds a _repo_root() helper in cli.py; tests monkeypatch it (no
env-var surface — preserves the .claude/CLAUDE.md invariant
that os.getenv() lives in startup_radar/config/ only).

Closes docs/AUDIT_FINDINGS.md §N (Resilience, local portion).
Cloud sync for backups deferred to Phase 9 (GH Actions DB
persistence).
```

Then tag: `STARTUP_RADAR_SHIP=1 git tag phase-6`.

---

## 4. Verification checklist

```bash
uv run startup-radar --help | grep -E '(backup|doctor|status)'
# expect: three lines, one per command

uv run startup-radar status
# expect: 5-line output; exit 0

uv run startup-radar doctor
# expect: header + ≥4 check lines + summary; exit 0 (or 1 with clear failures)

uv run startup-radar doctor --network
# expect: same but with HTTP probe details per enabled source

uv run startup-radar backup
# expect: backups/startup-radar-<ts>.tar.gz; tar -tzf shows db + config + tokens

uv run startup-radar backup --db-only
# expect: tarball containing only startup_radar.db

tar -tzf backups/startup-radar-*.tar.gz | head
# expect: startup_radar.db, config.yaml, token.json, credentials.json

git check-ignore backups/
# expect: exit 0 (ignored)

make ci
# expect: green; ≥28 tests
```

---

## 5. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | `_repo_root()` helper drifts from real `__file__`-based path if cli.py moves within the package | Low | Tests + commands resolve wrong dir | Tests monkeypatch the helper, so real drift would show up at runtime first (status/backup/doctor against a non-existent path). Add a smoke assertion in `test_cli_status.py` that the unpatched helper points at the real repo root. |
| 2 | `Source.healthcheck` signature change breaks a source not yet migrated in the Phase 6 diff | Certain if diff is partial | `doctor` raises AttributeError | All 4 sources ship in the same commit (§3.3 parallel edits). The ABC default `(True, ...)` makes any missed override fail-closed at "OK" rather than crash. |
| 3 | `doctor --network` hits SEC EDGAR without UA header and gets 403 | Medium | False-negative failure noise | §2.4's sec_edgar override explicitly passes `User-Agent: self._user_agent()` — same header the real `fetch()` uses. |
| 4 | Tarball in `backups/` grows unbounded and the user doesn't notice | Certain | Disk usage accumulates | Phase 9 auto-rotation deferred. For now, `status` surfaces `DB size` but NOT `backups/ size` — add in Phase 9 or via a one-line doc in README. |
| 5 | `backup` includes `token.json` and user accidentally shares the tarball | Low-Medium | OAuth token leakage | `--no-secrets` flag is documented and in `--help` output. README calls this out explicitly. Default INCLUDES secrets because the common case is "my disk died, I need to restore"; user must opt out if sharing. |
| 6 | CliRunner-based tests fail on CI because SQLite / filesystem mtime has second-granularity and `last run` shows as "0s ago" | Low | Flaky test | `_format_age(0)` returns `"0s ago"`; test asserts on `"ago"` substring, not exact value. |
| 7 | `requests.head` against one of the default RSS feeds returns 405 Method Not Allowed | Medium | False-negative in `doctor --network` | §2.4 treats `<400` as OK, but 405 is `<500` and some servers do return it. Fix: fall back to `requests.get(..., stream=True)` with `r.close()` on 405. Acceptable risk — document in README if observed. |
| 8 | `--db-only` with missing config.yaml returns exit 1 because `load_config()` fails early in `_backup` | Medium | User can't back up DB if config broken | Wrap `load_config()` in try/except (see §2.1 snippet — `except Exception: db_path = repo_root / "startup_radar.db"`). Fallback is the default path. |
| 9 | `sqlite3.connect(":memory:")` is implied if DB path is missing; `status` then shows all-zero counts instead of "—" | Low | Misleading output | §2.3's `_status` checks `db_path.exists()` before connecting; missing DB → `DB size: —`, all counts stay at `0`. Acceptable: zero rows IS the truth for a missing DB from the user's POV. |
| 10 | `backup --output /dev/null` or other invalid path | Low | Tarfile raises | Stdlib error bubbles up. Acceptable — user bug. `mkdir(parents=True, exist_ok=True)` covers the common typo case. |
| 11 | `doctor` in CI (GH Actions) times out on the `requests.head` calls behind a corporate proxy | Low | CI flake | `--network` is opt-in; daily.yml does NOT pass it. CI runs `doctor` (fast) if it adopts pre-flight in Phase 9. |
| 12 | `logs/` directory doesn't exist on a fresh install | Certain | `status` prints `Last run: never` | Expected behavior. Not an error. |
| 13 | `subprocess.check_output(["git", ...])` fails in a non-git tarball install (e.g. `pipx install git+...`) | Medium | `status` shows "(not a git repo)" | §2.3 catches `SubprocessError | FileNotFoundError` and falls back to `"(not a git repo)"`. Not an error. |
| 14 | `startup_radar.__version__` import fails in editable-dev mode if setuptools-scm hasn't run | Low | `status` shows `Version: unknown` | §2.3 catches `ImportError` and falls back. Non-fatal. |
| 15 | Existing tests in `tests/` break because the new `conftest.py` auto-imports | Low | CI red | `fake_repo` is a named fixture, not autouse. Existing tests that don't request it are unaffected. Verified by running `pytest` after 3.6 but before any existing test edits. |

---

## 6. Done criteria

- [ ] `startup_radar/cli.py` exposes `backup`, `doctor`, `status` commands; `--help` lists all three with one-line descriptions.
- [ ] `_repo_root()` helper in `cli.py`; no env-var surface; tests monkeypatch it.
- [ ] `Source.healthcheck(cfg, *, network=False) -> tuple[bool, str]` in the ABC; all 4 sources override it.
- [ ] `uv run startup-radar status` exits 0 against the real repo and prints branch/version/last-run/DB counts.
- [ ] `uv run startup-radar doctor` exits 0 or 1 with a rendered report; `--network` triggers HTTP probes against enabled sources.
- [ ] `uv run startup-radar backup` produces `backups/startup-radar-<ts>.tar.gz` containing the DB + config + secrets; `--no-secrets` drops OAuth files; `--db-only` drops everything except the DB.
- [ ] `backups/` and `*.tar.gz` in `.gitignore`.
- [ ] `tests/test_cli_backup.py`, `tests/test_cli_doctor.py`, `tests/test_cli_status.py`, `tests/conftest.py` present; ≥12 new tests, all green under `make ci`.
- [ ] `.claude/CLAUDE.md` quickref table lists the three commands.
- [ ] `.claude/rules/sources.md` documents the new `healthcheck()` signature.
- [ ] `.claude/settings.json` allowlist includes the three new `Bash(uv run startup-radar ...)` permissions.
- [ ] `.claude/hooks/pre-commit-check.sh` refuses `backups/**` paths.
- [ ] `AGENTS.md`, `README.md` updated.
- [ ] `docs/AUDIT_FINDINGS.md` — new §N (Resilience) → RESOLVED for local backup; cloud-sync open for Phase 9.
- [ ] `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 8 → ✅; §0a Adds row `backup` → ✅.
- [ ] `docs/plans/phase-6.md` (this file) present.
- [ ] Commit tagged `phase-6`.

---

## 7. What this enables

- **Phase 7 (`startup-radar init` wizard):** wizard's final step invokes `doctor` automatically and shows green/red to the user. Failure path points to concrete fixups.
- **Phase 8 (schedule install):** `scheduling/*` unit templates can pre-flight `doctor` before `run` on each tick. Opt-in via a template flag.
- **Phase 9 (GH Actions DB persistence):** `backup` becomes the primitive for the commit-to-data-branch option — `gh workflow run` can tar + push the archive, and a separate action can restore it. `status` provides the health-check surface for the workflow's final step.
- **Phase 11 (dashboard decomposition):** `status` JSON (deferred) feeds a System Health page directly.
- **Phase 12 (Storage + migrator):** `backup` / restore becomes lossless — `PRAGMA user_version` in the archive header lets restore refuse mismatched schemas rather than silently breaking.
- **Phase 13 (structlog + per-source counters):** `status` gains per-source success/fail counters from the `runs` table. The minimal log-mtime surface in Phase 6 is the path of least regret.
