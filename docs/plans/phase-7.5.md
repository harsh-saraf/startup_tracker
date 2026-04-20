# Phase 7.5 Execution Plan — Skills Layer (natural-language CLI)

> Wrap every user-facing CLI command and the new Phase 7 data-branch operations as Claude Code skills (`.claude/skills/<name>/SKILL.md`). The target user opens Claude Code and types `/something` — they don't run `git checkout --orphan data` or memorize Typer flags. Phase 7 left two human-only steps (data-branch bootstrap + local restore) and the existing CLI (`run`, `serve`, `doctor`, `status`, `backup`) has no slash-command equivalents. Both gaps close here.

## Phase summary

- **Add 7 skills** under `.claude/skills/`:
  - `/data-branch-bootstrap` — interactive orphan-branch creation + push (sanctioned exception to "no git push" rule, gated by handshake env-var like `/ship`).
  - `/data-branch-restore` — `git fetch origin data:data && git checkout data -- startup_radar.db`, then runs `startup-radar status` to confirm.
  - `/run` — wraps `uv run startup-radar run` with sensible defaults; offers `--scheduled` if user mentions cron/automation.
  - `/serve` — wraps `uv run startup-radar serve`, opens browser hint, watches for "Streamlit ready" line.
  - `/doctor` — wraps `uv run startup-radar doctor [--network]`; explains failures in plain English.
  - `/backup` — wraps `uv run startup-radar backup [--no-secrets] [--db-only]`; asks user about secrets posture.
  - `/status` — wraps `uv run startup-radar status`; renders a 1-line summary + a tip if last-run is stale.
- **Harness changes** to allow `/data-branch-bootstrap` to push:
  - New env-var handshake `STARTUP_RADAR_DATA_BOOTSTRAP=1` (mirrors `STARTUP_RADAR_SHIP=1` from `/ship`).
  - `pre-bash.sh` hook gains a one-liner: allow `git push origin data` and `git push --set-upstream origin data` ONLY when `STARTUP_RADAR_DATA_BOOTSTRAP=1` is set on the same command.
  - Settings allow-list adds `Bash(git push origin data*)` (denied by default; the hook is the gate).
  - `.claude/CLAUDE.md` "Do NOT delegate" entry for git pushes gets an exception note pointing at the skill.
- **No code changes to `startup_radar/`**. All CLI surfaces already exist.
- **Docs**:
  - `README.md` — refresh "Claude Code skills" section to list the new slash commands.
  - `docs/ops/data-branch.md` — add "or just run `/data-branch-bootstrap` in Claude Code" at the top of the bootstrap section; keep the manual fallback for users running outside Claude.
- **Tests** — none. Skills are markdown specs, not code; verifying them means actually invoking them in Claude Code (manual smoke per §3.6).

## Out of scope (deferred)

| Item | Deferred to | Why |
|---|---|---|
| `/setup-radar` rewrite to call new skills internally | Phase 8 (init wizard) | Setup wizard is its own large refactor; touching it here doubles scope. |
| `/add-source` skill | Phase 10 | Pairs with the source-implementer subagent + vcrpy fixtures; meaningless without test scaffolding. |
| `/deepdive` rewrite | never | Already exists, already works. |
| `/ship` rewrite | never | Already exists, already works. |
| `/sync` skill (pull data branch into a local clone for inspection) | Phase 12 | Pairs with storage migrator — naive DB overwrite can break the dashboard, same reason restore CLI was deferred from Phase 6. |
| Auto-invocation of `/doctor` on session start | never | The session-init hook already prints DB row counts; auto-running `doctor` on every session is friction. |
| `/data-branch-gc-trigger` | never | One-line `gh workflow run data-branch-gc.yml`; not worth a skill, and the cron handles it. |
| Streamlit GUI buttons that invoke skills | never | Out of scope; Claude Code is the natural-language layer, the dashboard is the GUI layer. |

## Effort estimate

- ~0.5 engineering day. Mostly markdown.
- Critical path: getting the `STARTUP_RADAR_DATA_BOOTSTRAP=1` handshake right in `pre-bash.sh` and verifying `/data-branch-bootstrap` actually pushes when invoked end-to-end.
- Secondary: writing 6 thin wrapper skills that don't drift from CLI flags over time. Mitigation: each skill's "Procedure" section is one `Bash` call, not a re-implementation.
- Tag at end: `phase-7.5`.

## Prerequisites

- ✅ Phase 7: `data` branch + workflow rewrite (this commit).
- ✅ `make ci` green at start; working tree clean except for Phase 7 deltas.
- No new runtime deps. No new GitHub secrets. No new harness deps.

---

## 1. Files to change

| Path | Action | Notes |
|---|---|---|
| `.claude/skills/data-branch-bootstrap/SKILL.md` | **create** | Interactive orphan-branch bootstrap. Uses `STARTUP_RADAR_DATA_BOOTSTRAP=1` handshake. ~80 lines. |
| `.claude/skills/data-branch-restore/SKILL.md` | **create** | Pull prod DB locally + verify via `status`. ~30 lines. |
| `.claude/skills/run/SKILL.md` | **create** | Thin wrapper. ~25 lines. |
| `.claude/skills/serve/SKILL.md` | **create** | Thin wrapper + dashboard URL hint. ~25 lines. |
| `.claude/skills/doctor/SKILL.md` | **create** | Thin wrapper + plain-English failure interpretation. ~35 lines. |
| `.claude/skills/backup/SKILL.md` | **create** | Wrapper + asks about secrets posture before invocation. ~35 lines. |
| `.claude/skills/status/SKILL.md` | **create** | Wrapper + staleness tip. ~25 lines. |
| `.claude/hooks/pre-bash.sh` | edit | Allow `git push origin data` and `git push --set-upstream origin data` when `STARTUP_RADAR_DATA_BOOTSTRAP=1` is set. |
| `.claude/settings.json` | edit | Add `Bash(STARTUP_RADAR_DATA_BOOTSTRAP=1 git push origin data*)` to allow-list. Mirrors the `STARTUP_RADAR_SHIP=1` pattern. |
| `.claude/CLAUDE.md` | edit | "Do NOT delegate" → add exception for `/data-branch-bootstrap` skill. |
| `README.md` | edit | "Claude Code skills" section: list new slash commands. |
| `docs/ops/data-branch.md` | edit | Add "Easiest path: run `/data-branch-bootstrap` in Claude Code" at top of bootstrap section. |
| `docs/plans/phase-7.5.md` | **create** | This document. |

### Files explicitly NOT to touch

- Anything under `startup_radar/` — phase is harness/skills only.
- `.github/workflows/*.yml` — Phase 7 work, no further changes.
- `database.py`, `app.py`, `connections.py` — no code path changes.
- `tests/**` — no new tests; skill verification is manual smoke.

---

## 2. Skill shapes (sketches, not final copy)

### 2.1 `/data-branch-bootstrap`

```yaml
---
name: data-branch-bootstrap
description: One-time creation of the orphan `data` branch on origin, used by GH Actions to persist the SQLite DB across runs. Sanctioned exception to the "no git push" rule via STARTUP_RADAR_DATA_BOOTSTRAP=1 handshake.
when_to_use: When the user says "bootstrap data branch", "/data-branch-bootstrap", "set up GH Actions persistence", or after a fresh fork / clone. NEVER auto-invoke. NEVER run if `git ls-remote --heads origin data` already returns a ref.
allowed-tools: [Bash, Read]
---
```

Procedure (high-level):
1. **Pre-flight.** Confirm working tree clean (`git status --porcelain` empty). Confirm `data` does not already exist on origin (`git ls-remote --heads origin data`). If either fails, STOP and surface the issue.
2. **Confirm with user.** Show them what's about to happen (orphan branch, single commit, push to origin). Ask "yes / cancel".
3. **Stash current branch name** so we can return to it (`git branch --show-current`).
4. **Create orphan + commit + push** via the handshake. The 6 commands from `docs/ops/data-branch.md` get prefixed with `STARTUP_RADAR_DATA_BOOTSTRAP=1` on the push line.
5. **Return to original branch.** `git checkout <stashed>`.
6. **Verify.** `git ls-remote --heads origin data` returns one ref; tell the user "data branch ready; next `daily.yml` run will commit your DB."
7. **Tell the user the second human step:** they must enable "Read and write permissions" under repo Settings → Actions → General. The skill cannot do this for them (no GH API permission); print the exact menu path.

### 2.2 `/data-branch-restore`

```yaml
---
name: data-branch-restore
description: Pull the latest production SQLite DB from the orphan `data` branch into the local working tree, then run `startup-radar status` to confirm row counts.
when_to_use: When the user says "restore prod db", "pull the latest data", "/data-branch-restore", or after wiping `startup_radar.db` locally.
allowed-tools: [Bash, Read]
---
```

Procedure (high-level):
1. **Warn if local DB has unsaved state.** `stat startup_radar.db` and warn user we're about to overwrite. Ask "yes / cancel".
2. **Fetch + checkout the file.**
   ```bash
   git fetch origin data:data
   git checkout data -- startup_radar.db
   ```
3. **Verify** via `uv run startup-radar status`. If row counts are all zeros, surface as "the prod DB on `data` branch appears empty — has the daily workflow run yet?"

No handshake needed — neither command is denied.

### 2.3 Thin CLI wrappers (`/run`, `/serve`, `/doctor`, `/backup`, `/status`)

Each follows the same pattern:

```yaml
---
name: <verb>
description: <one-line>
when_to_use: When the user says "<verb>", "/<verb>", or asks to <action> in plain English.
allowed-tools: [Bash]
---

# /<verb>

Wraps `uv run startup-radar <verb> [flags]`.

## Procedure

1. If user mentioned a flag (e.g. "--network" for /doctor, "--no-secrets" for /backup), set it.
2. Run the command.
3. Interpret the output for the user — don't dump raw stdout if it exits non-zero. Translate exit codes to plain English ("doctor flagged a missing credential at <path>; fix by …").
```

Skill-specific notes:
- **`/serve`**: Streamlit blocks the foreground. Use `run_in_background: true` on the Bash call (or print the URL and tell the user to open it; the user kills the dev server when done). Probably background-it.
- **`/backup`**: ALWAYS ask about `--no-secrets` posture before running. If the user says "I'm sharing this", force `--no-secrets`. If they say "personal disaster recovery", default `--include-secrets`.
- **`/doctor`**: Default to fast mode. Only pass `--network` if user explicitly asks for "deep" or "network" check.
- **`/status`**: After the wrapped call, if last-run is >48h old, suggest "want me to /run?".
- **`/run`**: If the user mentions "cron", "scheduled", "automated", pass `--scheduled`.

### 2.4 `pre-bash.sh` diff (sketch)

Add alongside the existing `STARTUP_RADAR_SHIP=1` handshake check:

```bash
# Allow data-branch bootstrap pushes via the documented handshake.
if [[ "$BASH_COMMAND" =~ ^STARTUP_RADAR_DATA_BOOTSTRAP=1[[:space:]]+git[[:space:]]+push[[:space:]]+(--set-upstream[[:space:]]+)?origin[[:space:]]+data($|[[:space:]]) ]]; then
  exit 0
fi
```

Exact regex/shell will be finalized during implementation; the contract is: handshake env-var on the same command, only matches `git push origin data` (no other refs, no force flag).

### 2.5 `.claude/CLAUDE.md` diff

```diff
 ## Do NOT delegate
 - Anything touching secrets, OAuth flows, or `config.yaml` writes — hand back to user.
-- Commits and pushes — surface diff, let the user run `git commit`.
+- Commits and pushes — surface diff, let the user run `git commit`. Two sanctioned exceptions: the `/ship` skill (commit only) and the `/data-branch-bootstrap` skill (one-shot push of the orphan `data` branch). Both gated by env-var handshakes the `pre-bash.sh` hook checks.
```

### 2.6 `README.md` diff

```diff
 ## Claude Code skills

-When you run `claude` from this project folder, two special commands are available:
-
-- **`/setup-radar`** — the setup wizard (first-time configuration)
-- **`/deepdive CompanyName`** — research any company and generate a one-page .docx brief scored against your criteria (e.g. `/deepdive Anthropic`)
+When you run `claude` from this project folder, the following slash commands are available:
+
+| Command | What it does |
+|---|---|
+| `/setup-radar` | First-time configuration wizard |
+| `/deepdive CompanyName` | One-page company research brief (.docx) |
+| `/run` | Run the discovery pipeline once |
+| `/serve` | Open the Streamlit dashboard |
+| `/doctor` | Validate config, credentials, network |
+| `/status` | Show last-run age + DB row counts |
+| `/backup` | Local tarball of DB + config + OAuth |
+| `/data-branch-bootstrap` | One-time GH Actions DB persistence setup (after fork) |
+| `/data-branch-restore` | Pull the latest prod DB from the cloud |
+| `/ship` | Run CI + commit (Claude/dev-only) |
```

### 2.7 `docs/ops/data-branch.md` diff

Prepend a "Easiest path" callout above the manual command block:

```diff
 ## First-time setup (run once per fork)

+**Easiest:** open Claude Code in the project folder and run `/data-branch-bootstrap`. The skill walks the same steps below interactively and only pushes after you confirm.
+
+If you'd rather do it manually:
+
 ```bash
 git checkout --orphan data
 …
```

---

## 3. Step-by-step execution

### 3.1 Pre-flight

```bash
git status                                       # phase-7 deltas only, or clean if Phase 7 already shipped
git log -1 --format='%h %s'
make ci                                          # green
grep -n 'STARTUP_RADAR_SHIP=1' .claude/hooks/pre-bash.sh   # confirm pattern exists to mirror
```

### 3.2 Write the 7 skills (parallel)

Spawn skill-author work in parallel (one Write call per file). Skills are independent — no shared state between them.

### 3.3 Edit `pre-bash.sh`

Single regex addition mirroring the existing `STARTUP_RADAR_SHIP=1` allowance. Verify by running:

```bash
STARTUP_RADAR_DATA_BOOTSTRAP=1 bash -c 'echo would-push'   # should not be denied by hook
bash -c 'git push origin data'                             # should be denied (no handshake)
```

Test the hook in isolation, NOT against origin. Use `--dry-run` if a real push would occur during smoke.

### 3.4 Edit `.claude/settings.json`

Add the handshake-allowed Bash pattern. Verify with `python -c 'import json; json.load(open(".claude/settings.json"))'`.

### 3.5 Docs (parallel)

Parallel `Edit` calls:
- `README.md` (skills table)
- `.claude/CLAUDE.md` (Do NOT delegate exception)
- `docs/ops/data-branch.md` (callout)

### 3.6 Manual smoke (in Claude Code)

The skills are markdown — only Claude can verify they work. Run, in order:

1. `/status` — confirm wrapper invokes CLI and renders 1-liner.
2. `/doctor` — confirm fast mode runs and exits 0.
3. `/backup` — confirm secrets-posture prompt fires; verify tarball lands in `backups/`.
4. `/run` — confirm pipeline runs; status reflects new rows.
5. `/serve` — confirm dashboard launches (background).
6. `/data-branch-restore` — only after Phase 7's daily workflow has run once on origin and committed a DB. Pre-Phase-7 this skill has nothing to fetch.
7. `/data-branch-bootstrap` — DESTRUCTIVE on a real fork. Test only on a throwaway fork OR after the user has confirmed origin's `data` branch is intentionally absent. Verify the handshake is required (try without it; should be denied by `pre-bash.sh`).

### 3.7 Ship + tag

```bash
/ship
git tag phase-7.5
git push origin phase-7.5
```

Suggested commit message:

```
feat(skills): wrap CLI + data-branch ops as Claude Code slash commands

Adds 7 skills under .claude/skills/ so users only ever type `/something`
in Claude Code instead of memorizing CLI flags or running git commands:

- /run, /serve, /doctor, /status, /backup — thin wrappers around the
  existing `startup-radar` CLI surfaces.
- /data-branch-bootstrap — one-shot orphan-branch creation on origin,
  gated by a STARTUP_RADAR_DATA_BOOTSTRAP=1 handshake in pre-bash.sh
  (mirrors the /ship pattern).
- /data-branch-restore — pulls the latest prod DB from the data branch
  + verifies via `startup-radar status`.

Closes the Phase 7 follow-up gap: the orphan-branch bootstrap and local
restore were human-only steps; the wrappers turn them into natural
language. README + CLAUDE.md + docs/ops/data-branch.md updated to point
users at the slash commands first; manual instructions retained as
fallback.
```

---

## 4. Verification checklist

- [ ] All 7 SKILL.md files present with valid frontmatter (`name`, `description`, `when_to_use`, `allowed-tools`).
- [ ] `pre-bash.sh` denies `git push origin data` without the handshake; allows it with.
- [ ] `.claude/settings.json` parses; new allow-list entry present.
- [ ] `.claude/CLAUDE.md` has the "Do NOT delegate" exception line for `/ship` + `/data-branch-bootstrap`.
- [ ] `README.md` skills section lists all 9 slash commands (2 existing + 7 new).
- [ ] `docs/ops/data-branch.md` opens with the `/data-branch-bootstrap` callout; manual block follows as fallback.
- [ ] Manual smoke per §3.6: `/status`, `/doctor`, `/backup`, `/run`, `/serve` all complete without harness errors.
- [ ] `/data-branch-restore` either fetches the DB OR cleanly reports "data branch is empty" if smoked before any daily run.
- [ ] `/data-branch-bootstrap` verified on a throwaway fork (or skipped during ship if no test fork available; document in commit body).
- [ ] `make ci` still green.
- [ ] Commit tagged `phase-7.5`.

---

## 5. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | `/data-branch-bootstrap` regex in `pre-bash.sh` is too permissive — accidentally allows pushing other branches with the handshake | Low | A future skill could push to main using the handshake | Regex anchored to `origin data($|[[:space:]])`. Code review the regex. Add a unit-style smoke in §3.3. |
| 2 | User invokes `/data-branch-bootstrap` on a fork where `data` already exists; the orphan would clobber it | Low | Existing DB history wiped | Pre-flight check `git ls-remote --heads origin data` STOPS the skill if a ref exists. |
| 3 | Skills drift from CLI flags as the CLI evolves | Medium | Skills suggest `--no-secrets` after we rename it | Each skill's procedure says "wrap `<command>`" not "duplicate its flags." When CLI flags change, grep for the skill name and update. Consider a `make verify-skills` that grep-asserts CLI surface in Phase 13. |
| 4 | `/serve` in background detaches and orphans the Streamlit process when Claude exits | Medium | User has to `pkill -f streamlit` | Document the kill command in the skill's "Cleanup" section. Or accept: they can `Ctrl-C` from the Bash output panel. |
| 5 | Users don't discover the slash commands because they're only in README | Medium | Phase 7.5 doesn't deliver the natural-language UX | `/setup-radar` (Phase 8) should print "you can also run /run, /doctor, /serve anytime in Claude" at the end of onboarding. Add as a TODO in Phase 8 plan. |
| 6 | `/data-branch-bootstrap` user agrees, push fails (network, perms) — orphan branch left in local state | Low | Working tree on orphan; user confused | Skill always returns to original branch in a `trap`-style cleanup block. Surface the push error verbatim. |
| 7 | Settings allow-list addition is too narrow and the actual command Claude generates doesn't match | Medium | Skill prompts user to approve every push | Pattern testing during §3.3 — exercise the exact command shape the skill produces. |

---

## 6. Done criteria

- [ ] 7 skills present under `.claude/skills/<name>/SKILL.md`.
- [ ] Handshake `STARTUP_RADAR_DATA_BOOTSTRAP=1` recognized by `pre-bash.sh`.
- [ ] Settings allow-list updated; JSON parses.
- [ ] CLAUDE.md "Do NOT delegate" lists both sanctioned exceptions.
- [ ] README skills table updated; `docs/ops/data-branch.md` leads with the slash command.
- [ ] All thin wrappers manually smoke-tested in Claude Code (§3.6 steps 1–5).
- [ ] `/data-branch-restore` smoke-tested OR explicit "deferred until first daily run lands" note in commit body.
- [ ] `/data-branch-bootstrap` smoke-tested on a throwaway fork OR explicit "untested live; gated behind handshake" note in commit body.
- [ ] `make ci` green.
- [ ] Commit tagged `phase-7.5`.

---

## 7. What this enables

- **Phase 8 (init wizard):** `/setup-radar` can call `/doctor`, `/data-branch-bootstrap`, and `/run` as substeps instead of inlining their procedures. Wizard becomes a sequencer.
- **Phase 10 (vcrpy + real source tests):** the `/add-source` skill (deferred from this phase) lands here. Pairs with the source-implementer subagent.
- **Phase 11 (dashboard decomposition):** "System Health" page can deep-link into "want to run /doctor?" via Streamlit's command-palette equivalent (a `st.markdown('Run `/doctor` in Claude Code')` line), keeping the GUI and CLI parallel.
- **Phase 14 (Dockerfile):** the same skills work inside the container — Claude Code mounts the project, the slash commands invoke `uv run` inside the container's venv. No skill changes needed.
