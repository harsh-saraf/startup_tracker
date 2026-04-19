# Phase 4 Execution Plan — Typer CLI + research/ subpackage + scm versioning

> Replace the three entry points (`main.py`, `daily_run.py`, `streamlit run app.py`) with one `startup-radar` console script. Re-home `deepdive.py` under `startup_radar/research/`. Attach `setuptools-scm` for git-tag versioning. Leaves `config.yaml` / `config_loader.py` / `filters.py` alone — those move in Phase 5 with the pydantic rewrite. Leaves `app.py` body untouched (multi-page split is Phase 11).

## Phase summary

- Add `typer>=0.12` as a runtime dep; add `setuptools-scm>=8` to `[build-system]`.
- Create `startup_radar/cli.py` — Typer app with three commands for Phase 4:
  - `startup-radar run [--scheduled]` — replaces `main.py` + `daily_run.py`. `--scheduled` mode sets up `logs/YYYY-MM-DD.log`, 15-minute timeout, stdout redirect (the current `daily_run.py` behavior).
  - `startup-radar serve [--port 8501]` — wraps `streamlit run app.py` so users don't type the streamlit invocation.
  - `startup-radar deepdive COMPANY` — calls `startup_radar.research.deepdive.generate(company)`.
- Create `startup_radar/research/{__init__.py,deepdive.py}` — move root `deepdive.py` verbatim, update 2 imports (`config_loader` stays flat at root).
- Register entry-point in `pyproject.toml`: `[project.scripts] startup-radar = "startup_radar.cli:app"`.
- Switch to `setuptools-scm` for version: `dynamic = ["version"]` at the top of `[project]` plus `[tool.setuptools_scm]` config block with `fallback_version = "0.1.0"` (for source checkouts with no tag history).
- Drop `main`, `daily_run`, `deepdive` from `[tool.setuptools] py-modules`; add `startup_radar.research` to `packages`.
- Repoint `app.py`'s `subprocess.Popen([sys.executable, "deepdive.py", ...])` at `app.py:803-814` to the new module entry: `[sys.executable, "-m", "startup_radar.cli", "deepdive", selected]`. Minimal diff — preserves the existing async polling + progress bar (`st.session_state["gen_proc"]` at line 811) rather than blocking the Streamlit rerun on a ~30-second call.
- Rewrite `.github/workflows/daily.yml`: `uv run python daily_run.py` → `uv run startup-radar run --scheduled`.
- Update scheduling templates (`scheduling/crontab.example`, `scheduling/launchd.plist.template`, `scheduling/windows_task.md`) to invoke `startup-radar run --scheduled`.
- Update `Makefile` `run` and `serve` targets to use the new CLI.
- Update harness + docs: `.claude/CLAUDE.md`, `.claude/settings.json` allow-list, `.claude/rules/observability.md`, `.claude/agents/source-implementer/SKILL.md`, `.claude/skills/deepdive/SKILL.md`, `AGENTS.md`, `README.md`, `docs/AUDIT_FINDINGS.md`, `docs/PRODUCTION_REFACTOR_PLAN.md`.
- Delete root `main.py`, `daily_run.py`, `deepdive.py` only after `make ci` is green with the new CLI.

## Out of scope (deferred)

| Item | Deferred to | Why |
|---|---|---|
| `startup-radar doctor` / `status` / `backup` | Phase 8 | Per refactor plan §0a re-ordered execution — backup/doctor/status are a dedicated phase after pydantic config lands. Cramming them into Phase 4 breaks the "one concern per phase" budget. |
| `startup-radar schedule install` | Phase 14 (Dockerfile / install tooling) | Current `scheduling/*` templates stay; CLI `schedule` verb is a full sub-app with OS detection logic — own phase. |
| `startup-radar init` (interactive wizard) | Phase 7 | Wizard writes `config.yaml` + `.env`; needs the pydantic schema to validate what it produced. |
| `startup-radar admin {migrate,reset,export}` | Phase 12 | Needs the `Storage` class + `PRAGMA user_version` migrator. |
| Pydantic-typed `cfg` on CLI commands | Phase 5 | `load_config()` still returns `dict[str, Any]` until Phase 5 rewrites it. |
| Rewrite `daily_run.py`'s `_LogStream` / stdout-redirect hack as structlog | Phase 13 | structlog phase replaces the whole pattern. Phase 4 preserves the workaround inside `cli.py`'s scheduled-mode path so logs keep landing in `logs/YYYY-MM-DD.log`. |
| Fix `threading.Timer` race (audit §12 item referenced in `docs/PRODUCTION_REFACTOR_PLAN.md` §0a adds, `daily_run.py:70`) | Phase 13 | Low-probability race; structured retry/observability phase owns it. Phase 4 carries the existing behavior forward unchanged. |
| Gmail token auto-refresh on expiry | Phase 13 | Per §0a adds list, Tier 3, paired with retries. |
| Move `filters.py` / `config_loader.py` / `connections.py` / `database.py` / `app.py` into the package | Phases 5 / 5 / 11 / 12 / 11 | Each has its own phase and diff footprint. Phase 4 resists the urge to "while we're at it." |
| Extra-safety mypy coverage on `cli.py` | Phase 13 | `cli.py` imports `startup_radar.sources.registry`, which pulls `requests` — `requests` has no type stubs, so mypy would go red. mypy scope stays `models.py` + `parsing/`. |

## Effort estimate

- 0.5–0.75 engineering day sequential (matches refactor plan §0a slot 6 estimate of 1 day — trimmed because Phase 3 already did the orchestration refactor).
- Critical path: `cli.py` scheduled mode (LOG_DIR, timeout, stdout redirect) behaving identically to `daily_run.py`, end-to-end through `make run`.
- Secondary path: `setuptools-scm` + dynamic version behaving correctly in `uv sync --all-extras` inside this git tree (tags `phase-0..3` exist; they are NOT semver — need `fallback_version` to avoid scm raising).
- Tag at end as `phase-4`.

## Prerequisites

- ✅ Phase 3: Source ABC + registry + parsing module (commit `84fe49b`, tag `phase-3`).
- ✅ `make ci` green at start.
- ✅ Working tree clean.
- ✅ `uv` on PATH (verified Phase 2).
- New deps to install: `typer>=0.12` (runtime), `setuptools-scm>=8` (build-system). Both resolve cleanly per quick `uv add --dry-run` check; no transitive-version risk documented in the refactor plan.

---

## 1. Files to change

| Path | Action | Notes |
|---|---|---|
| `startup_radar/cli.py` | **create** | Typer app. `run`, `serve`, `deepdive` commands. Scheduled-mode logging path folded in. ~140 lines. |
| `startup_radar/research/__init__.py` | **create** | Docstring only. |
| `startup_radar/research/deepdive.py` | **create** (moved) | Verbatim content of root `deepdive.py`, with `from config_loader import load_config` unchanged (still flat at root until Phase 5). Module-level `REPORTS_DIR = Path(__file__).parent / "reports"` → `Path.cwd() / "reports"` so reports still land at repo root, not inside the package. |
| `deepdive.py` | **delete** | After all callers updated. |
| `main.py` | **delete** | Logic folds into `cli.py` `run()` command. |
| `daily_run.py` | **delete** | Logic folds into `cli.py` `run(--scheduled)` code path. |
| `app.py` | edit | Line 805 subprocess args only: `"deepdive.py"` → `"-m", "startup_radar.cli", "deepdive"`. The `Popen` + progress-bar loop at 803-814 is preserved. No other changes. |
| `pyproject.toml` | edit | Add `typer` to `dependencies`; add `setuptools-scm` to `[build-system] requires`; add `dynamic = ["version"]`; drop `version = "0.1.0"`; add `[tool.setuptools_scm]`; add `[project.scripts]`; update `[tool.setuptools]` packages + py-modules. |
| `Makefile` | edit | `run:` → `uv run startup-radar run`; `serve:` → `uv run startup-radar serve`. Keep existing help text shape. |
| `.github/workflows/daily.yml` | edit | `uv run python daily_run.py` → `uv run startup-radar run --scheduled`. |
| `scheduling/crontab.example` | edit | `/usr/bin/env python3 daily_run.py` → `startup-radar run --scheduled`. |
| `scheduling/launchd.plist.template` | edit | `<string>PATH_TO_REPO/daily_run.py</string>` → `<string>startup-radar</string>` + args `["run", "--scheduled"]`. |
| `scheduling/windows_task.md` | edit | Arguments `daily_run.py` → `run --scheduled`; program becomes `startup-radar.exe`. |
| `.claude/CLAUDE.md` | edit | Repo layout section: kill `main.py`/`daily_run.py`/`deepdive.py` from root; add `startup_radar/cli.py` and `startup_radar/research/deepdive.py`. Common commands: add `startup-radar run|serve|deepdive`. Gotchas: CLI installed via `[project.scripts]`; running `uv sync --all-extras` refreshes the shim. Invariant: `print()` allowed only in `startup_radar/cli.py`, `startup_radar/research/deepdive.py`, and `tests/` (the old `main.py`/`daily_run.py` allowance goes away). |
| `.claude/settings.json` | edit | Drop `Edit(main.py)` / `Edit(daily_run.py)` / `Edit(deepdive.py)` from allow-list (files no longer exist). The broader `Edit(startup_radar/**)` + `Write(startup_radar/**)` already cover the replacements. |
| `.claude/rules/observability.md` | edit | Update the `print()` allow-list line: `startup_radar/cli.py` + `startup_radar/research/deepdive.py` + `tests/` replace the old `main.py` / `daily_run.py` / `deepdive.py` exceptions. |
| `.claude/hooks/pre-commit-check.sh` | edit | Line 24 `LIBRARY_PY` grep-exclude regex: swap `^(main\.py\|daily_run\.py\|deepdive\.py\|tests/\|\.claude/)` for `^(startup_radar/cli\.py\|startup_radar/research/deepdive\.py\|tests/\|\.claude/)`. Keeps the Stop hook's `print()` allow-list aligned with the observability rule. |
| `.claude/agents/source-implementer/SKILL.md` | edit | §Process step 6: `make run` → `startup-radar run`. (Smoke-verify line only.) |
| `.claude/skills/deepdive/SKILL.md` | edit | Swap any `deepdive.py` references to `startup-radar deepdive <Company>` where the skill's shell example lives. |
| `AGENTS.md` | edit | Commands cheat-sheet: `python main.py` → `startup-radar run`; also add `startup-radar serve`, `startup-radar deepdive`. "Do not add new top-level scripts; extend `main.py` or the (forthcoming) Typer CLI." → "...extend `startup_radar/cli.py` (the Typer CLI, since Phase 4)." |
| `README.md` | edit | Lines 125, 150, 153: `python daily_run.py` / `python main.py` → `startup-radar run`. |
| `docs/AUDIT_FINDINGS.md` | edit | §Entry points (HIGH row, §1) → marked RESOLVED (Phase 4). §Packaging (HIGH row, §10) — update the outstanding line to reflect `[project.scripts]` + `setuptools-scm` landing here. |
| `docs/PRODUCTION_REFACTOR_PLAN.md` | edit | §0a re-ordered execution row 6 marked ✅ done; note tag `phase-4`. |
| `docs/plans/phase-4.md` | create | This document. |

### Files explicitly NOT to touch

- `config_loader.py` — Phase 5 replaces it with pydantic. No imports churn now to avoid a re-rewrite next phase.
- `filters.py` — Phase 5.
- `database.py` — Phase 12.
- `connections.py` — Phase 11.
- `sinks/google_sheets.py` — no change. `cli.py run()` still imports it lazily via `from sinks import google_sheets` when the config enables it.
- `startup_radar/sources/**` — untouched. Phase 3 closed this out.
- `startup_radar/parsing/**` — untouched.
- `startup_radar/models.py` — untouched.
- `.claude/hooks/session-init.sh`, `.claude/hooks/pre-bash.sh`, `.claude/hooks/post-edit.sh` — no change. (`pre-commit-check.sh` DOES change — see §1.)
- `[tool.mypy] files` list — stays `["startup_radar/models.py", "startup_radar/parsing"]`. Do NOT add `cli.py` (transitively imports `requests`, which lacks stubs).

---

## 2. New file shapes

### 2.1 `startup_radar/cli.py`

```python
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


def _pipeline() -> int:
    """The actual pipeline. Mirrors pre-Phase-4 main.py:run()."""
    import database
    from config_loader import load_config
    from filters import StartupFilter
    from startup_radar.models import Startup
    from startup_radar.parsing.normalize import dedup_key
    from startup_radar.sources.registry import SOURCES

    print("=" * 60)
    print("Startup Radar")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    cfg = load_config()
    output_cfg = cfg.get("output", {})
    sqlite_cfg = output_cfg.get("sqlite", {})
    if sqlite_cfg.get("enabled", True) and sqlite_cfg.get("path"):
        database.set_db_path(sqlite_cfg["path"])
    database.init_db()

    all_startups: list[Startup] = []
    sources_cfg = cfg.get("sources", {})
    for key, source in SOURCES.items():
        if not sources_cfg.get(key, {}).get("enabled"):
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
        s for s in deduped
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

    sheets_cfg = output_cfg.get("google_sheets", {})
    if sheets_cfg.get("enabled") and fresh:
        try:
            from sinks import google_sheets
            google_sheets.append_startups(sheets_cfg["sheet_id"], fresh)
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
        typer.Option("--scheduled", help="Log to logs/YYYY-MM-DD.log with a 15-min timeout (cron mode)."),
    ] = False,
) -> None:
    """Run the discovery pipeline once."""
    if not scheduled:
        raise typer.Exit(code=_pipeline())

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
        rc = _pipeline()
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
    app_path = repo_root / "app.py"
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


if __name__ == "__main__":
    app()
```

### 2.2 `startup_radar/research/deepdive.py`

Verbatim move of root `deepdive.py`, except:
- `REPORTS_DIR = Path(__file__).parent / "reports"` → `REPORTS_DIR = Path.cwd() / "reports"` so reports land at repo root, not inside the installed package (which breaks for `pipx`/`uv tool` installs where the package lives in a venv).
- Drop the `__main__` block (`cli.py deepdive` is the entry point now).
- Keep `print()` calls — this module is in the CLI-user-visible tier per observability rule.

### 2.3 `pyproject.toml` diff

```diff
 [build-system]
-requires = ["setuptools>=68", "wheel"]
+requires = ["setuptools>=68", "setuptools-scm>=8", "wheel"]
 build-backend = "setuptools.build_meta"

 [project]
 name = "startup-radar"
-version = "0.1.0"
+dynamic = ["version"]
 description = "Personal startup discovery radar with Streamlit dashboard"
 readme = "README.md"
 requires-python = ">=3.10"
 license = { text = "MIT" }
 dependencies = [
     "pyyaml>=6.0",
     "requests>=2.31.0",
     "feedparser>=6.0.10",
     "beautifulsoup4>=4.12.0",
     "python-dateutil>=2.8.2",
     "pandas>=2.0.0",
     "streamlit>=1.30.0",
     "duckduckgo-search>=6.0.0",
     "python-docx>=1.1.0",
+    "typer>=0.12",
 ]

+[project.scripts]
+startup-radar = "startup_radar.cli:app"
+
 [project.optional-dependencies]
 google = [ ... ]

 [tool.uv]
 dev-dependencies = [ ... ]

+[tool.setuptools_scm]
+fallback_version = "0.1.0"
+# Existing tags are phase-0..3 (not semver); scm will emit dev-style versions
+# like "0.1.0.dev{N}+g{sha}" from HEAD. Fallback keeps source-tarball builds sane.
+
 [tool.setuptools]
 packages = [
     "startup_radar",
     "startup_radar.sources",
     "startup_radar.parsing",
+    "startup_radar.research",
 ]
 py-modules = [
-    "main", "daily_run", "app", "deepdive",
+    "app",
     "database", "filters",
     "config_loader", "connections",
 ]
```

> Version strategy: `setuptools-scm` with a `fallback_version` is the least-surprising shape — builds outside a git checkout still succeed. Actual CLI usage doesn't care about the version string today; `__version__` wiring into `--version` surfaces via Phase 8 (`startup-radar status`).

### 2.4 `Makefile` edits

```diff
 run:  ## Run the discovery pipeline once
-	uv run python main.py
+	uv run startup-radar run

 serve:  ## Start the Streamlit dashboard
-	uv run streamlit run app.py
+	uv run startup-radar serve
```

### 2.5 GH Actions edit (`.github/workflows/daily.yml`)

```diff
- run: uv run python daily_run.py
+ run: uv run startup-radar run --scheduled
```

### 2.6 Scheduling-template edits

- `scheduling/crontab.example`:
  ```diff
  -0 8 * * * cd /path/to/startup-radar-template && /usr/bin/env python3 daily_run.py >> logs/cron.log 2>&1
  +0 8 * * * cd /path/to/startup-radar-template && /path/to/venv/bin/startup-radar run --scheduled >> logs/cron.log 2>&1
  ```
- `scheduling/launchd.plist.template`: `<string>PATH_TO_REPO/daily_run.py</string>` → `<string>PATH_TO_VENV/bin/startup-radar</string>` + `<string>run</string>` + `<string>--scheduled</string>`.
- `scheduling/windows_task.md`: program = `startup-radar.exe`, arguments = `run --scheduled`.

### 2.7 `app.py` subprocess repoint

```diff
                 if st.button("Generate DeepDive Report", key="deepdive_btn"):
                     proc = subprocess.Popen(
-                        [sys.executable or "python", "deepdive.py", selected],
+                        [sys.executable or "python", "-m", "startup_radar.cli", "deepdive", selected],
                         cwd=str(PROJECT_DIR),
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         text=True,
                     )
```

> The existing shape polls `session_state["gen_proc"]` across Streamlit reruns and shows a progress bar (lines 787-801). Swapping to in-process `generate()` would block the rerun for 30+ seconds — materially worse UX. Repointing the subprocess to the CLI module preserves the async behavior. Phase 11 can revisit once the dashboard is decomposed.

---

## 3. Step-by-step execution

### 3.1 Pre-flight

```bash
git status                               # clean
git log -1 --format='%h %s'              # 84fe49b feat(sources)...
git tag --list 'phase-*'                 # phase-0 phase-1 phase-2 phase-3
make ci                                  # green
```

If not: STOP and surface.

### 3.2 Scaffold `startup_radar/research/` and move `deepdive.py`

```bash
mkdir -p startup_radar/research
git mv deepdive.py startup_radar/research/deepdive.py
```

Edit `startup_radar/research/__init__.py` to a single-line docstring. Edit `startup_radar/research/deepdive.py`:
- `REPORTS_DIR` → `Path.cwd() / "reports"`.
- Drop `if __name__ == "__main__":` block.

Smoke:
```bash
uv run python -c "from startup_radar.research.deepdive import generate; print(generate)"
```

### 3.3 Write `startup_radar/cli.py`

Per §2.1. Single `Write` call.

Smoke (before entry-point wiring):
```bash
uv run python -m startup_radar.cli --help
uv run python -m startup_radar.cli run --help
```

### 3.4 Update `pyproject.toml`

Per §2.3. Add `typer` via `uv add`:
```bash
uv add 'typer>=0.12'
```

Then apply the rest via Edit (build-system, dynamic version, scripts, setuptools_scm, packages, py-modules).

Re-sync:
```bash
uv sync --all-extras
uv run startup-radar --help              # entry-point reachable
```

If `setuptools-scm` errors about non-semver tags: confirm `fallback_version` is set; per scm docs it falls back when `get_version()` fails. If it still errors, add `local_scheme = "no-local-version"` to `[tool.setuptools_scm]`.

### 3.5 Wire app.py + scheduling + Makefile + GH Actions

Parallel Edit calls:
- `app.py` (§2.7)
- `Makefile` (§2.4)
- `.github/workflows/daily.yml` (§2.5)
- `scheduling/crontab.example`, `scheduling/launchd.plist.template`, `scheduling/windows_task.md` (§2.6)

Smoke:
```bash
make run                                 # pipeline end-to-end; tolerates missing config
make serve                               # streamlit boots; ctrl-c to exit
uv run startup-radar deepdive "Anthropic"
```

> `make serve` only verifies the CLI→streamlit bridge; the dashboard itself is Phase 11's concern. A 2-second `streamlit is starting` then ctrl-c is enough.

### 3.6 Delete the old entry points

```bash
git rm main.py daily_run.py
```

> `deepdive.py` was already `git mv`-ed in step 3.2.

### 3.7 Full local CI

```bash
make ci                                  # ruff + format-check + mypy + pytest
```

Any red: STOP. See §6 risks.

### 3.8 Update harness + docs

Parallel Edit calls per §1 "Files to change". Specifically:
- `.claude/CLAUDE.md`: repo layout tree + common-commands + invariant on `print()` allow-list.
- `.claude/settings.json`: strip obsolete root-file allow-entries.
- `.claude/rules/observability.md`: `print()` allow-list line.
- `.claude/agents/source-implementer/SKILL.md`: `make run` → `startup-radar run` in step 6.
- `.claude/skills/deepdive/SKILL.md`: invocation references.
- `AGENTS.md`: commands cheat-sheet + the "extend main.py" line.
- `README.md`: `python main.py` / `python daily_run.py` → `startup-radar run`.
- `docs/AUDIT_FINDINGS.md`: §Entry points → RESOLVED (Phase 4); §Packaging → updated.
- `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 6 → ✅ done + `phase-4` tag.

### 3.9 Ship

Use `/ship`. Suggested commit message:

```
feat(cli): introduce Typer CLI + research/ subpackage + scm versioning

Replaces three entry points (main.py, daily_run.py, streamlit run app.py)
with one `startup-radar` console script exposing run / serve / deepdive.
`run --scheduled` folds daily_run.py's log-file + timeout + stdout-redirect
behavior so cron/launchd/GH Actions keep writing logs/YYYY-MM-DD.log.

Re-homes deepdive.py under startup_radar/research/ — first occupant of the
subpackage per refactor-plan §3.1.

Switches pyproject.toml to setuptools-scm with fallback_version; drops the
hardcoded version = "0.1.0". Registers [project.scripts] startup-radar =
"startup_radar.cli:app".

Closes docs/AUDIT_FINDINGS.md §1 (entry points) and the packaging portion
of §10. Defers doctor/status/backup (Phase 8), schedule install (Phase 14),
pydantic-typed cfg (Phase 5), and the structlog rewrite of scheduled-mode
logging (Phase 13).
```

Then tag: `STARTUP_RADAR_SHIP=1 git tag phase-4`.

---

## 4. Verification checklist

Between 3.7 and 3.9, confirm each:

```bash
uv run startup-radar --help              # shows three subcommands
uv run startup-radar run --help          # --scheduled flag visible
uv run startup-radar deepdive --help     # company arg visible
uv run startup-radar serve --help        # --port option visible
uv run startup-radar run --scheduled     # writes logs/YYYY-MM-DD.log, exits 0/1
ls logs/$(date +%Y-%m-%d).log            # log file exists after scheduled run
make ci                                  # green
git grep -nE 'python main\.py|python daily_run\.py|python deepdive\.py' -- ':!docs/' ':!.claude/CLAUDE.md' ':!docs/plans/'
# expect: zero matches (docs + this plan legitimately reference the old commands)
test ! -f main.py && test ! -f daily_run.py && test ! -f deepdive.py && echo "roots deleted"
```

---

## 5. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | `setuptools-scm` rejects the `phase-*` tag format and fails without hitting `fallback_version` | Medium | `uv sync` / `pip install -e .` fail | scm's `fallback_version` is documented to trigger on `LookupError` (no version found). Non-semver tags typically yield a derived `dev` version; if scm rejects, add `local_scheme = "no-local-version"` and/or explicit `version_scheme = "no-guess-dev"`. Verify in 3.4 before moving on. |
| 2 | `[project.scripts]` shim not refreshed after `uv sync` — `startup-radar` not on PATH | Medium | Every verification command fails | `uv sync --all-extras` re-installs in editable mode. If still missing: `uv pip install -e . --reinstall`. |
| 3 | `cli.py` scheduled-mode behavior diverges from `daily_run.py` — log file shape changes | Medium | Breaks users who grep their logs | §2.1 copies the `_setup_logging` / `_LogStream` / timer code verbatim. Diff the log file from a pre-Phase-4 run vs post on the same config to confirm identical. |
| 4 | `REPORTS_DIR = Path.cwd() / "reports"` breaks when `startup-radar deepdive` is run from an unrelated directory | Low | Report saved to user's cwd instead of repo | Acceptable — user expectation for a CLI tool. Old behavior (`Path(__file__).parent`) would write into the venv for `pipx` installs, which is worse. Document in the commit body. |
| 5 | `app.py`'s new in-process `generate()` blocks the Streamlit event loop for 30+ seconds | Medium | Dashboard appears frozen during a deepdive | Wrap in `with st.spinner("Researching..."):`. The old subprocess shape had the same UX problem silently; new shape at least shows progress. |
| 6 | Dropping `Edit(main.py)` etc. from settings.json allow-list mid-session doesn't take effect until restart | Certain | Cosmetic — the files don't exist anyway | Per Phase 1 risk #13 note. No action needed. |
| 7 | Stop-hook regex swap lands in wrong spot — the `|` is shell-glob-escaped differently from the in-code POSIX regex | Low | Hook silently no-ops, stops flagging `print()` in library code | Script uses `grep -Ev '^(a\|b\|c)'` (alternation). Echo the line after edit and eyeball; smoke by touching `startup_radar/sources/rss.py` with a `print()` and running the hook manually. |
| 8 | `typer>=0.12` transitively pulls `click`/`rich` versions that conflict with `streamlit` | Low | `uv sync` resolution error | typer 0.12 → click 8.x, rich 13.x; streamlit 1.30 → click 8.x, rich 13.x. Compatible. If conflict: drop to `typer>=0.9` which uses `click 7.x`. |
| 9 | `uv run startup-radar ...` is slower than `uv run python main.py` on cold start | Low | ~200ms user-visible lag | typer + click import is ~100-200ms on cold venv. Accept; this is a personal tool. |
| 10 | `Annotated[... typer.Option(...)]` syntax needs `from typing import Annotated` which was added in 3.9 — project targets `>=3.10` | Low | Compatible | 3.10+ fine. No action. |
| 11 | Integration: `sinks/google_sheets.py` is still imported lazily inside `_pipeline()` — if the move breaks the import, scheduled runs fail silently | Low | Google Sheets sink stops working | Lazy import pattern preserved from original `main.py:94`. |
| 12 | `mypy` scope doesn't catch type bugs in `cli.py` | Certain | Acceptable — per constraint | Deliberate: `cli.py` transitively imports `requests`; expanding mypy reveals non-actionable "missing stubs" noise. Revisit Phase 13. |

---

## 6. Done criteria

- [ ] `startup_radar/cli.py` exists with three commands (`run`, `serve`, `deepdive`). `run` supports `--scheduled`.
- [ ] `startup_radar/research/__init__.py` + `startup_radar/research/deepdive.py` exist. Old root `deepdive.py` deleted.
- [ ] `main.py` + `daily_run.py` deleted.
- [ ] `pyproject.toml` has `dynamic = ["version"]`, `[tool.setuptools_scm]`, `[project.scripts]`, `typer` in `dependencies`, `setuptools-scm` in `[build-system] requires`, `startup_radar.research` in `packages`, and no `main`/`daily_run`/`deepdive` in `py-modules`.
- [ ] `uv sync --all-extras` succeeds end-to-end; `uv run startup-radar --help` prints three subcommands.
- [ ] `uv run startup-radar run --scheduled` writes `logs/YYYY-MM-DD.log` and exits 0 (given a valid config).
- [ ] `make ci` passes (test count unchanged vs Phase 3; this phase adds no tests — the CLI is a thin shim over `_pipeline()`).
- [ ] `make run` / `make serve` still work (via the new CLI).
- [ ] `app.py`'s subprocess-call site is gone; dashboard DeepDive button calls `generate()` in-process.
- [ ] `.github/workflows/daily.yml`, `scheduling/*` templates reference `startup-radar run --scheduled`.
- [ ] `.claude/CLAUDE.md`, `.claude/settings.json`, `.claude/rules/observability.md`, `.claude/hooks/pre-commit-check.sh`, `.claude/agents/source-implementer/SKILL.md`, `.claude/skills/deepdive/SKILL.md` updated to the new layout.
- [ ] `AGENTS.md`, `README.md` updated.
- [ ] `docs/AUDIT_FINDINGS.md` §1 (Entry points) → RESOLVED (Phase 4); §10 packaging lines reflect `[project.scripts]` + `setuptools-scm` landed here.
- [ ] `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 6 → ✅ done.
- [ ] `docs/plans/phase-4.md` (this file) present.
- [ ] Commit tagged `phase-4`.

---

## 7. What this enables

- **Phase 5 (pydantic config + `.env`):** `cli.py`'s commands take a typed `AppConfig` instead of `dict[str, Any]`. The `_pipeline()` inner swap is one annotation change.
- **Phase 7 (`startup-radar init` wizard):** slots in alongside existing commands — pydantic schema validates what the wizard writes.
- **Phase 8 (`doctor` / `status` / `backup`):** three new `@app.command()` decorators in `cli.py`. No scaffolding work.
- **Phase 11 (dashboard split):** `startup-radar serve` stays the single entry point; under the hood it may switch from `streamlit run app.py` to `streamlit run startup_radar/web/Home.py` without users noticing.
- **Phase 13 (structlog):** the `_LogStream` / `_setup_scheduled_logging` hack in `cli.py` gets replaced wholesale. No callers need updating — they just invoke `startup-radar run --scheduled` and keep getting log-file output.
- **Phase 14 (`schedule install`):** `cli.py` gains a `schedule` sub-app that generates the OS-specific scheduler entry (crontab line / launchd plist / schtasks) on the fly instead of shipping static templates.
