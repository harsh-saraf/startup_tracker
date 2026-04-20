# Phase 7 Execution Plan — GH Actions DB Persistence (commit-to-data-branch)

> Replace the unsound `actions/cache`-keyed-by-`run_id` scheme in `.github/workflows/daily.yml` with a deterministic commit-to-`data`-branch scheme. DB survives across runs, is observable via `git log data -- startup_radar.db`, and requires no new infrastructure or API keys. Closes Tier 0 bug #1 and the GH Actions item in `docs/AUDIT_FINDINGS.md` §3.

## Phase summary

- **Rewrite `.github/workflows/daily.yml`** to:
  1. `actions/checkout@v4` the `main` branch (workflow + deps + code).
  2. `actions/checkout@v4` the `data` branch into `./.data/` (as a second checkout via `path:`). If the branch does not yet exist, skip this step and start fresh.
  3. Copy `.data/startup_radar.db` → `startup_radar.db` at repo root before the pipeline runs (so `load_config().output.sqlite.path` resolves as today).
  4. Run the pipeline (`uv run startup-radar run --scheduled`) exactly as today.
  5. Run `uv run startup-radar status` as a post-step for observability in the Actions log.
  6. Copy `startup_radar.db` back into `./.data/startup_radar.db`.
  7. Commit + push the updated DB to the `data` branch via `EndBug/add-and-commit@v9` (pinned by SHA) with a deterministic commit message `chore(data): pipeline run ${{ github.run_id }} (${{ github.run_started_at }})`.
  8. Upload `startup_radar.db` and `logs/` as workflow artifacts (retention 7 days) — short-term recovery if the `data` branch is force-pushed or corrupted.
- **Weekly GC workflow** (`.github/workflows/data-branch-gc.yml`) — separate workflow, `schedule: 0 9 * * 0` (Sundays 09:00 UTC). Force-pushes a fresh orphan commit on `data` with only the latest DB + a `README.md` pointer, discarding binary-diff bloat per `docs/CRITIQUE_APPENDIX.md` §5. Non-destructive for callers: anyone who has the DB downloaded is unaffected; subsequent daily runs re-checkout a clean orphan.
- **One-time bootstrap doc** — a `docs/ops/data-branch.md` page with the three commands needed to create the orphan branch the first time. Not a script (too easy to footgun; bootstrap happens once per fork).
- **No code changes to `startup_radar/`** — the workflow is the whole change. `status` and `backup` already work against whatever DB is on disk.
- **Docs** — `README.md` gains a short "GH Actions persistence" section; `docs/AUDIT_FINDINGS.md` §3 → RESOLVED; `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 9 → ✅; `docs/CRITIQUE_APPENDIX.md` §5 is already prescriptive, leave as-is.
- **Harness** — `.claude/settings.json` gets no new permissions (workflow runs in CI, not on dev machine). `CLAUDE.md` gains a one-line gotcha about the `data` branch so future-Claude doesn't delete it.

## Out of scope (deferred)

| Item | Deferred to | Why |
|---|---|---|
| S3 / Turso / GH Releases alternatives | never | `docs/CRITIQUE_APPENDIX.md` §5 directs: pick **one**. commit-to-data-branch wins on free + observable + recoverable. |
| Encrypted DB-at-rest on the `data` branch | never | `startup_radar.db` contains scraped public news. No PII per `docs/CRITIQUE_APPENDIX.md` §12. Encryption adds key-management burden for zero risk reduction. |
| `startup-radar sync` / `startup-radar restore` CLI to pull the `data` branch locally | Phase 12 | Pairs with the storage migrator — naive DB overwrite can silently break the dashboard (`docs/plans/phase-6.md` §"Out of scope" row 1). User's workaround today: `git fetch origin data:data && git checkout data -- startup_radar.db`. |
| Auto-restore of a prior DB on pipeline failure | Phase 13 | Requires structured logging + per-source failure counters to decide "the pipeline failed badly enough that we should not commit the DB." Phase 7's rule is simpler: if `run` exits 0, commit. |
| Tests for the workflow itself (e.g. `act`-based) | never | The workflow is 40 lines of YAML wiring existing actions; meaningful tests would require running GH Actions in a container. Smoke-testable via `workflow_dispatch`. `actionlint` in CI (Phase 10 CI scaffolding) catches syntax. |
| Signed commits on the `data` branch | never | Single-user tool; commits are GH-Actions-bot-authored; signing adds GPG key management for no gain. |
| Concurrent-run lockout | Phase 13 | `actions/concurrency: group: daily-run cancel-in-progress: true` — one-liner, but out of scope here. Today only one `schedule` + `workflow_dispatch` can overlap; in practice it won't. |
| Commit back to `main` instead of `data` | never | Binary diffs would bloat the main branch history. `data` is orphan for that reason. |
| Retention policy beyond weekly GC | Phase 13 | Structured runs table will hold per-run metadata; `data` branch only needs the latest DB. |

## Effort estimate

- ~1 engineering day per `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 9.
- Critical path: getting the orphan `data` branch bootstrapped and proving the second-checkout-with-`path:` flow works end-to-end via `workflow_dispatch`.
- Secondary path: writing the GC workflow and verifying the force-push preserves the latest DB byte-for-byte.
- No new Python code, no new tests inside `tests/`, no schema changes.
- Tag at end: `phase-7`.

## Prerequisites

- ✅ Phase 6: backup/doctor/status commands (commit `85ff8f9`, tag `phase-6`).
- ✅ `make ci` green at start; working tree clean.
- ✅ Repo has `CONFIG_YAML`, `CREDENTIALS_JSON`, `TOKEN_JSON` secrets already (same as today's `daily.yml`).
- No new runtime deps, no new GitHub secrets.
- `EndBug/add-and-commit@v9` — popular, MIT-licensed, already-vetted action. Pin by SHA in the workflow per GitHub's security guidance.

---

## 1. Files to change

| Path | Action | Notes |
|---|---|---|
| `.github/workflows/daily.yml` | edit | Full rewrite per §2.1. ~65 lines (up from 63). |
| `.github/workflows/data-branch-gc.yml` | **create** | Weekly force-push GC per §2.2. ~40 lines. |
| `docs/ops/data-branch.md` | **create** | One-time orphan-branch bootstrap instructions per §2.3. ~30 lines. |
| `README.md` | edit | Add "GH Actions scheduling & persistence" subsection under Deployment. Point at `docs/ops/data-branch.md`. |
| `docs/AUDIT_FINDINGS.md` | edit | §3 GH-Actions-cache item → RESOLVED (Phase 7). |
| `docs/PRODUCTION_REFACTOR_PLAN.md` | edit | §0a row 9 → ✅ done. §1 Tier 0 bug #1 → ✅ fixed. |
| `docs/plans/phase-7.md` | **create** | This document. |
| `.claude/CLAUDE.md` | edit | Add gotcha: "Never delete or force-push the `data` branch from local — it's the production DB store. Phase 7." Common-commands table: add `git fetch origin data:data && git checkout data -- startup_radar.db` as the restore-from-prod snippet. |

### Files explicitly NOT to touch

- Any file under `startup_radar/` — phase is workflow-only.
- `database.py`, `app.py`, `connections.py` — no code path changes; DB is just at a different *source* by the time the pipeline reads it.
- `config.yaml`, `config.example.yaml` — no shape changes; `output.sqlite.path` stays `startup_radar.db`.
- `scheduling/*` (cron/launchd templates) — unchanged. Local scheduling has no `data` branch equivalent; `backup` covers local resilience.
- `tests/**` — no new tests. The workflow is wiring-only; unit tests would be noise.
- `.claude/settings.json` — no new `Bash(...)` permissions. `git fetch origin data:data` is already permitted under the existing `Bash(git *)` allowlist entry (verify during §3.1).
- `.github/workflows/ci.yml` — CI is Phase-10 scope; do not conflate.

---

## 2. New/changed file shapes

### 2.1 `.github/workflows/daily.yml` (full rewrite)

```yaml
name: Daily Startup Radar

on:
  schedule:
    # 15:00 UTC daily = 08:00 PT / 11:00 ET. Edit to taste.
    - cron: '0 15 * * *'
  workflow_dispatch: {}

# Only one pipeline run at a time; a newer schedule tick cancels a stuck older one.
concurrency:
  group: daily-run
  cancel-in-progress: false

permissions:
  contents: write      # required to push to the `data` branch

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Checkout main
        uses: actions/checkout@v4

      - name: Checkout data branch (DB store)
        uses: actions/checkout@v4
        with:
          ref: data
          path: .data
        continue-on-error: true     # first run, before `data` exists

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Restore DB from data branch
        run: |
          if [ -f ".data/startup_radar.db" ]; then
            cp .data/startup_radar.db startup_radar.db
            echo "Restored DB from data branch: $(stat -c %s startup_radar.db) bytes"
          else
            echo "No prior DB found on data branch — starting fresh."
          fi

      - name: Write config
        # CONFIG_YAML / CREDENTIALS_JSON / TOKEN_JSON live in repo secrets; see README.
        run: |
          echo "$CONFIG_YAML" > config.yaml
          if [ -n "$CREDENTIALS_JSON" ]; then echo "$CREDENTIALS_JSON" > credentials.json; fi
          if [ -n "$TOKEN_JSON" ]; then echo "$TOKEN_JSON" > token.json; fi
        env:
          CONFIG_YAML: ${{ secrets.CONFIG_YAML }}
          CREDENTIALS_JSON: ${{ secrets.CREDENTIALS_JSON }}
          TOKEN_JSON: ${{ secrets.TOKEN_JSON }}

      - name: Doctor (fast)
        run: uv run startup-radar doctor

      - name: Run pipeline
        run: uv run startup-radar run --scheduled

      - name: Status (post-run observability)
        if: always()
        run: uv run startup-radar status

      - name: Stage DB for data branch
        if: success()
        run: |
          mkdir -p .data
          cp startup_radar.db .data/startup_radar.db

      - name: Commit DB to data branch
        if: success()
        uses: EndBug/add-and-commit@a94899bca583c204427a224a7af87c02f9b325d5   # v9.1.4
        with:
          default_author: github_actions
          new_branch: data
          cwd: .data
          add: startup_radar.db
          message: "chore(data): pipeline run ${{ github.run_id }} (${{ github.run_started_at }})"
          push: true

      - name: Upload database artifact (short-term recovery)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: startup-radar-db
          path: startup_radar.db
          retention-days: 7

      - name: Upload logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: logs
          path: logs/
          retention-days: 7
```

Notes:
- `permissions: contents: write` is the minimum scope — no `id-token`, no `pull-requests`, no `pages`.
- Two checkouts into different paths is an `actions/checkout` supported pattern; `path: .data` isolates the `data` branch worktree cleanly.
- `continue-on-error: true` on the second checkout is the bootstrap case. `EndBug/add-and-commit@v9` then creates `data` via `new_branch: data` on the first successful run.
- SHA pin (`a94899bca583...`) per GitHub's recommendation; the tag comment `# v9.1.4` preserves readability.
- `if: success()` on both "Stage" and "Commit" means a pipeline failure leaves `data` untouched — the prior DB wins, and the failed run is visible via the artifact upload + the action log.
- `uv run startup-radar doctor` gives a fast pre-flight line in the actions log without hitting the network. Phase 8 may move this to `doctor --network` once we know how EDGAR's UA-checked endpoint responds from GH's IP space.

### 2.2 `.github/workflows/data-branch-gc.yml` (new, weekly GC)

```yaml
name: Data-branch GC

on:
  schedule:
    - cron: '0 9 * * 0'     # Sundays 09:00 UTC
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  gc:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Checkout data branch
        uses: actions/checkout@v4
        with:
          ref: data
          path: .data
        continue-on-error: true

      - name: Force-push fresh orphan commit
        run: |
          if [ ! -f ".data/startup_radar.db" ]; then
            echo "No data branch or no DB; nothing to GC."
            exit 0
          fi
          cd .data
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          # New orphan history with only the current DB.
          git checkout --orphan data-new
          git rm -rf --cached . || true
          git add startup_radar.db
          printf '# startup-radar data branch\n\nOrphan branch holding the latest pipeline DB. Weekly GCd. See docs/ops/data-branch.md on main.\n' > README.md
          git add README.md
          git commit -m "chore(data): weekly GC $(date -u +%Y-%m-%d)"
          git branch -M data-new data
          git push --force origin data
```

Notes:
- Anyone with the DB already downloaded is unaffected. Subsequent daily runs pick up the orphan and keep appending.
- `continue-on-error` + the `-f` existence check means the GC is idempotent on a repo that hasn't bootstrapped `data` yet.
- Runtime: <10s. Cost: negligible. Risk: force-push of `data` — acceptable by design (the branch is single-writer, and anyone cloning it for restore does so at a point in time).

### 2.3 `docs/ops/data-branch.md` (new, bootstrap doc)

```markdown
# `data` branch — GH Actions DB store

Startup Radar's GitHub Actions workflow persists the SQLite DB (`startup_radar.db`) by committing it to an orphan branch named `data`. This doc is the one-time bootstrap for a fresh fork.

## Why a branch, not cache?

See `docs/CRITIQUE_APPENDIX.md` §5. TL;DR: `actions/cache` is evicted at 7 days no-access and racy across concurrent runs. A git branch is free, observable (`git log data -- startup_radar.db`), and recoverable.

## First-time setup (run once per fork)

```bash
# Create an orphan `data` branch with no history.
git checkout --orphan data
git rm -rf .                               # strip everything from the index
printf '# startup-radar data branch\n' > README.md
git add README.md
git commit -m "chore(data): initialize orphan data branch"
git push origin data

# Back to main.
git checkout main
```

After that, the daily workflow will commit `startup_radar.db` to `data` automatically.

## Manual restore (pull the prod DB locally)

```bash
git fetch origin data:data
git checkout data -- startup_radar.db
# Now `startup_radar.db` at repo root is the latest prod DB.
```

## Garbage collection

A separate workflow (`.github/workflows/data-branch-gc.yml`) force-pushes a fresh orphan commit every Sunday to prevent binary-diff bloat. If you never want GC, delete that workflow — the DB will still persist, but the branch history will grow indefinitely.

## Failure modes

- **Pipeline fails** → no commit to `data`; prior DB stays as-is. Failed run's partial DB is in the `startup-radar-db` artifact (7-day retention).
- **`data` branch deleted accidentally** → next run starts fresh, same as a new fork. No data rescue from the branch; use the most recent `startup-radar-db` artifact (Actions → workflow run → Artifacts).
- **Force-push from elsewhere** → last writer wins. GC workflow is the only force-pusher by design.
```

### 2.4 `README.md` additions

Append under a new "Deployment — GH Actions" subsection (exact placement TBD during execution):

```markdown
### GH Actions scheduling & persistence

`.github/workflows/daily.yml` runs `startup-radar run --scheduled` on a cron schedule and persists `startup_radar.db` by committing it to an orphan `data` branch. First-time setup requires creating the `data` branch once — see `docs/ops/data-branch.md`.

To restore the prod DB locally:

```bash
git fetch origin data:data
git checkout data -- startup_radar.db
```

A separate weekly workflow (`data-branch-gc.yml`) force-pushes a fresh orphan commit on `data` to prevent binary-diff bloat.
```

### 2.5 `.claude/CLAUDE.md` diff

```diff
 ## Gotchas
+- `data` branch (GH Actions DB store, Phase 7) — NEVER delete, rebase, or force-push from a developer machine. The daily workflow writes to it; the weekly GC workflow is the only sanctioned force-pusher. To pull the prod DB locally: `git fetch origin data:data && git checkout data -- startup_radar.db`.
 - `feedparser` does NOT take a `timeout` kwarg — …
```

### 2.6 `docs/AUDIT_FINDINGS.md` diff

```diff
 ### 3. Database & persistence (HIGH)
-- **GH Actions cache is broken**: `.github/workflows/daily.yml:24-29` keys cache by `${{ github.run_id }}` (always unique)…
+- ✅ **RESOLVED (Phase 7)** — `.github/workflows/daily.yml` rewritten to commit `startup_radar.db` to an orphan `data` branch via `EndBug/add-and-commit@v9`. Weekly GC in `.github/workflows/data-branch-gc.yml` prevents bloat. See `docs/ops/data-branch.md` for the one-time bootstrap.
```

### 2.7 `docs/PRODUCTION_REFACTOR_PLAN.md` diff

```diff
-| 9 | GH Actions DB persistence via commit-to-data-branch | 1 day | Pick **one** option. |
+| 9 | ✅ GH Actions DB persistence via commit-to-data-branch | 1 day | **DONE Phase 7** — `daily.yml` rewrite + `data-branch-gc.yml` weekly force-push + `docs/ops/data-branch.md` bootstrap. Tag: `phase-7`. |
```

```diff
-| 1 | **GH Actions DB persistence broken** — cache key uses `${{ github.run_id }}` … | `.github/workflows/daily.yml:24-29` | Drop `actions/cache`; commit DB to a `data` branch via `EndBug/add-and-commit`, or push to S3/Turso/GH Releases. Without this every "daily" run starts fresh. |
+| 1 | ✅ **FIXED (Phase 7)** GH Actions DB persistence via commit-to-`data`-branch + weekly orphan GC. |
```

---

## 3. Step-by-step execution

### 3.1 Pre-flight

```bash
git status                               # clean
git log -1 --format='%h %s'              # 85ff8f9 feat(cli):...
git tag --list 'phase-*'                 # phase-0..6
make ci                                  # green

# Confirm .claude/settings.json already allows `Bash(git fetch *)` and
# `Bash(git checkout *)` for the local-restore path in CLAUDE.md. If not,
# do NOT add them in this phase — just document the commands.
grep -n '"Bash(git' .claude/settings.json
```

### 3.2 Bootstrap the `data` branch (destructive-ish; do this first)

Human runs these (not Claude — branch creation on a shared remote is out of scope for the harness per `.claude/CLAUDE.md` "Do NOT delegate"):

```bash
git checkout --orphan data
git rm -rf .
printf '# startup-radar data branch\n' > README.md
git add README.md
git commit -m "chore(data): initialize orphan data branch"
git push origin data
git checkout refactor/v2
```

Verify:

```bash
git ls-remote --heads origin data        # one ref printed
```

### 3.3 Rewrite `.github/workflows/daily.yml`

Single edit per §2.1. Diff should be ~full-file since the shape changes significantly; use `Write` (after `Read`), not incremental `Edit`.

### 3.4 Create `.github/workflows/data-branch-gc.yml`

`Write` per §2.2.

### 3.5 Create `docs/ops/data-branch.md`

`mkdir -p docs/ops` (via shell), then `Write` per §2.3.

### 3.6 Docs + harness edits (parallel)

Parallel `Edit` calls:
- `README.md` (add §2.4 subsection)
- `.claude/CLAUDE.md` (§2.5 diff)
- `docs/AUDIT_FINDINGS.md` (§2.6 diff)
- `docs/PRODUCTION_REFACTOR_PLAN.md` (§2.7 diff)

### 3.7 Local smoke (no GH run)

```bash
# Confirm yaml is syntactically valid.
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/daily.yml'))"
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/data-branch-gc.yml'))"

# If actionlint is available locally, run it; otherwise rely on GH's own parser.
which actionlint && actionlint .github/workflows/daily.yml .github/workflows/data-branch-gc.yml || echo "(actionlint not installed)"

make ci                                  # green; no test changes expected
```

### 3.8 Ship + trigger a manual run

```bash
# Via /ship skill (sanctioned pathway).
/ship
```

Suggested commit message:

```
feat(ci): commit DB to data branch for GH Actions persistence

Replaces the broken actions/cache-keyed-by-run_id scheme with a
deterministic commit-to-`data`-branch scheme via EndBug/add-and-commit.

- daily.yml:
  - Checks out main + data branch (the latter into .data/).
  - Restores startup_radar.db from data before the pipeline runs.
  - Runs `startup-radar doctor` as a fast pre-flight.
  - On success, copies the updated DB back and commits it to `data`.
  - Still uploads DB + logs as 7-day artifacts for short-term recovery.
  - Adds concurrency group + 20min timeout.

- data-branch-gc.yml (new): weekly Sunday 09:00 UTC orphan force-push
  to prevent binary-diff bloat on the data branch.

- docs/ops/data-branch.md: one-time bootstrap + manual-restore
  instructions.

Closes the GH Actions DB-persistence item in docs/AUDIT_FINDINGS.md §3
and Tier 0 bug #1 in docs/PRODUCTION_REFACTOR_PLAN.md.
```

Then after merge to `main`:

```bash
git tag phase-7
git push origin phase-7

# Smoke the workflow manually (do NOT wait for the cron to fire).
gh workflow run daily.yml
gh run watch                             # confirm green; artifact uploaded; data branch has one new commit

# Confirm persistence by triggering a second run and diffing.
gh workflow run daily.yml
gh run watch
git fetch origin data
git log origin/data -- startup_radar.db  # expect ≥2 commits
```

---

## 4. Verification checklist

```bash
# 1. Workflow YAML parses and lints.
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/daily.yml'))"
which actionlint && actionlint .github/workflows/*.yml

# 2. `data` branch exists on origin.
git ls-remote --heads origin data

# 3. First daily run commits a new blob to `data`.
gh workflow run daily.yml
gh run watch
git fetch origin data
git log origin/data --oneline | head -5

# 4. Second run picks up the prior DB.
#    In the run's "Restore DB from data branch" step log, expect:
#        "Restored DB from data branch: N bytes"  (not "starting fresh")

# 5. Status step renders DB row counts in the action log (not all zeros).

# 6. GC workflow dispatches green.
gh workflow run data-branch-gc.yml
gh run watch

# 7. After GC, data branch has ONE commit (orphan).
git fetch origin data
git log origin/data --oneline | wc -l    # expect 1

# 8. Local restore flow works.
git fetch origin data:data
git checkout data -- startup_radar.db
uv run startup-radar status              # expect non-zero row counts
git checkout -- startup_radar.db         # revert — don't commit DB to refactor branch
```

---

## 5. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | `EndBug/add-and-commit@v9` is abandoned / SHA disappears | Low | Workflow fails on `Commit DB` step | Pinned by SHA (not tag) per GitHub security guidance. If abandoned, swap for a `git add && git commit && git push` shell step; wiring is 10 lines. |
| 2 | Two concurrent `daily.yml` runs both try to push `data` → one loses with non-fast-forward | Medium (low with cron only; higher with manual dispatches) | One run's DB is discarded | `concurrency.group: daily-run` + `cancel-in-progress: false` (wait, don't preempt). The second run rebases via `EndBug/add-and-commit`'s default pull-rebase behavior, but if the DB file changed on both sides, the newer wins (binary merge is undefined). Accept: for a daily-scheduled + rare-manual-dispatch tool, collision is ~annual. If it becomes common, add a mutex via a "lock" file on the `data` branch. |
| 3 | `EndBug/add-and-commit` detects no change (DB byte-identical) and skips the commit | Certain on a day with no new signals | No new commit on `data` | Expected, not a bug. `status` still runs; next day's run re-restores the same DB. |
| 4 | `data` branch grows to GB-scale due to binary-diff inefficiency | Low (mitigated by GC) | Slow clones | Weekly force-push GC (§2.2). Between GCs, 7 commits × ~1 MB DB ≈ 7 MB; git stores whole blobs for binaries so history is at most `sum(DB_size_each_day)`. Acceptable. |
| 5 | First `daily.yml` run after phase ships fails because `data` doesn't exist yet | Certain if §3.2 skipped | Red first run | §3.2 is a human prereq (documented in `docs/ops/data-branch.md`). `continue-on-error: true` on the second checkout degrades to "fresh start" instead of crashing. |
| 6 | `EndBug/add-and-commit` runs `cwd: .data` but the action pulls origin/main by default, causing a checkout swap | Low | DB committed to main, not data | Action's `cwd` is the *working directory*, and our `.data/` directory is already checked out to the `data` branch via `actions/checkout` with `ref: data path: .data`. Action's internal `git push` uses the current branch of `cwd`. Smoke via §3.8 second run before trusting. |
| 7 | The workflow's `CONFIG_YAML` secret hasn't been rotated in months, contains a stale `output.sqlite.path` | Low | DB written to a different path than restored | `config.example.yaml` defaults to `startup_radar.db`; stale configs pin the same. Risk is synthetic. |
| 8 | `startup-radar doctor` in fast mode discovers a config issue and exits 1, blocking the pipeline | Medium (if config drifted) | Workflow red, no commit | **This is the intended behavior** — a broken config is worse than a missed run. Human sees the doctor output in the run log and fixes `CONFIG_YAML`. If this becomes too aggressive, add `continue-on-error: true` to the doctor step; do NOT remove it outright. |
| 9 | GC workflow races with `daily.yml` at the top of a Sunday (both fire around 09:00-15:00 UTC) | Low (6h gap by design) | GC force-pushes over a just-committed DB | Schedules are non-overlapping by 6h. If drift occurs, the daily run's DB lands on the orphan on Monday; loss is at most 1 day's delta. Acceptable. |
| 10 | `permissions: contents: write` is set repo-wide in repo settings to `read` only | Low | Push to `data` fails | Error is immediate and loud (`403` in action log). Fix: repo → Settings → Actions → General → "Read and write permissions" for the default `GITHUB_TOKEN`. Document in `docs/ops/data-branch.md`. |
| 11 | First `status` step after restore fails because the DB schema predates Phase 6's `connections` table expectation | Low | Red step, but *after* pipeline ran | `_status` in `cli.py:28x` already wraps each table query in `try/except sqlite3.OperationalError` (`docs/plans/phase-6.md` §2.3). Falls back to `—`. Non-fatal. |
| 12 | `actions/checkout@v4` with a non-existent `ref: data` on a fork that hasn't bootstrapped fails HARD even with `continue-on-error` | Low | First run fails instead of degrading | `continue-on-error: true` is respected by the action itself, not just by step-level error propagation. Verified in GH Actions docs. If it turns out not to work: fallback is an explicit `if: success()`-gated `gh api` call to check for the ref first. |
| 13 | Someone rebases `main` onto `data` by typing `git checkout data` by muscle memory | Low | Binary DB in main history | `.claude/CLAUDE.md` gotcha is the only mitigation. No pre-commit hook adds for free here without blocking legitimate `data` access. Accept as a human-error risk. |
| 14 | Artifact retention of 7 days + weekly GC means any DB more than 7 days old is unrecoverable | Certain by design | Long-term rollback impossible | Acceptable per `docs/CRITIQUE_APPENDIX.md` §12 ("anything that prevents data loss … is worth the effort" — we prevent **recent** data loss; deep history is out of scope for a personal tool). Phase 6 `backup` covers local snapshots for user who care. |
| 15 | `github.run_started_at` is missing on very old GH-Actions runners | Low | Commit message is malformed | Output is cosmetic. If it breaks, swap for `$(date -u +%Y-%m-%dT%H:%M:%SZ)` via a shell step. |

---

## 6. Done criteria

- [ ] `.github/workflows/daily.yml` rewritten per §2.1: two-checkout flow, DB restore from `data`, doctor pre-flight, pipeline run, status post-step, commit to `data`, artifact upload.
- [ ] `.github/workflows/data-branch-gc.yml` present per §2.2; weekly cron + `workflow_dispatch`.
- [ ] `docs/ops/data-branch.md` present; covers bootstrap, restore, failure modes, and "where did my DB go" FAQ.
- [ ] `README.md` links to `docs/ops/data-branch.md` under a "GH Actions scheduling & persistence" subsection.
- [ ] `.claude/CLAUDE.md` has the `data`-branch gotcha line.
- [ ] `docs/AUDIT_FINDINGS.md` §3 GH-Actions-cache item → RESOLVED (Phase 7).
- [ ] `docs/PRODUCTION_REFACTOR_PLAN.md` §0a row 9 and §1 Tier 0 bug #1 → ✅.
- [ ] `data` branch exists on `origin` (human bootstrap; verifiable via `git ls-remote --heads origin data`).
- [ ] `gh workflow run daily.yml` → green; run N+1 logs show "Restored DB from data branch: … bytes" (not "starting fresh").
- [ ] `gh workflow run data-branch-gc.yml` → green; `data` branch has exactly 1 commit after GC.
- [ ] Local restore `git fetch origin data:data && git checkout data -- startup_radar.db` works; `startup-radar status` reports non-zero rows.
- [ ] `make ci` still green (no test changes; workflow is wiring-only).
- [ ] Commit tagged `phase-7`.

---

## 7. What this enables

- **Phase 8 (init wizard):** wizard's "green first run" flow can include a `git push origin data` step after orphan-branch creation, automating the §3.2 bootstrap. Optional; CLI wizard can emit the three commands for the user to copy.
- **Phase 10 (vcrpy fixtures + real source tests):** CI now has a stable DB surface to diff against; cassette-backed tests can commit deterministic DB state to a test-specific branch if needed. Unlikely but available.
- **Phase 11 (dashboard decomposition):** a "System Health" page can add "last successful pipeline run" by parsing the `data` branch's latest commit timestamp via the GitHub API. No new backend surface.
- **Phase 12 (Storage + migrator):** `PRAGMA user_version` enforcement becomes meaningful because restore is now a real path. Restore CLI (deferred from Phase 6) lands here, paired with the migrator — the migrator refuses mismatched versions rather than silently breaking the dashboard.
- **Phase 13 (structlog + per-source counters):** structured logs upload as artifacts with richer retention; per-source failure counters live in a new `runs` table inside the DB, surviving via the `data` branch for free. No additional persistence mechanism needed.
