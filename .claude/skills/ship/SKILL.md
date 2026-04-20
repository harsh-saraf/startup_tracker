---
name: ship
description: Run full local CI, draft a conventional commit message from the staged diff, and commit it. Sanctioned commit pathway (the only way Claude is allowed to invoke `git commit` in this repo).
when_to_use: When the user explicitly says "ship", "commit this", "/ship", or after a unit of work is complete and ready to land. NEVER auto-invoke.
allowed-tools: [Bash, Read, Glob, Grep]
---

# /ship — sanctioned commit pathway

The `pre-bash.sh` hook denies bare `git commit *`. This skill is the **only** sanctioned path for Claude to commit, via the `STARTUP_RADAR_SHIP=1` env-var handshake.

## Procedure

### 1. Verify CI is green
Run:
```bash
make ci
```
If anything fails, **STOP**. Surface the output to the user. Do NOT proceed to commit. Fix issues first.

### 2. Inspect what's about to land
Run in parallel:
```bash
git status --short
git diff --stat HEAD
git log -1 --format='%h %s'
```
If `git status` is empty → nothing to commit; STOP and tell the user.

### 3. Read the actual diff for message authoring
```bash
git diff HEAD
```
Skim the diff. Do NOT skip this — the commit message must reflect what actually changed, not what you intended to change.

### 4. Draft a Conventional Commits message
Format: `<type>(<scope>): <subject>` with optional body.

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `style`, `ci`.

Subject:
- ≤72 chars
- Imperative mood ("add", "fix", not "added", "fixes")
- Lowercase first letter, no trailing period

Body (optional, wrap at 72 chars):
- WHY the change, not WHAT (the diff shows what)
- Reference the plan / phase / file paths if non-obvious
- One paragraph per logical group

Footer (mandatory):
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### 5. Show the user the message + ask for confirmation

Print the proposed message clearly. Then ASK:
> Commit with this message? (yes / edit / cancel)

- **yes** → proceed to step 6
- **edit** → take user's revised message and use it
- **cancel** → STOP. No commit.

If the user invoked `/ship` non-interactively (e.g., via a script or the user's intent is obviously "just ship it"), you may skip the confirmation, but only if the user's prior message was an explicit go-ahead like "ship it", "commit and tag", "lfg", etc.

### 6. Stage + commit (with the handshake)

If the user wants specific files only, stage those. Otherwise:
```bash
STARTUP_RADAR_SHIP=1 git add -A
```

Then commit using a HEREDOC for proper formatting:
```bash
STARTUP_RADAR_SHIP=1 git commit -m "$(cat <<'EOF'
<type>(<scope>): <subject>

<body>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

The `STARTUP_RADAR_SHIP=1` prefix MUST be on the same command as `git commit` for the hook to allow it.

### 7. Verify
```bash
git log -1 --format='%h %s'
git status
```
Confirm the commit landed and the working tree is clean.

### 8. Optional: tag

If the commit completes a Phase per `docs/plans/phase-N.md`, tag it:
```bash
STARTUP_RADAR_SHIP=1 git tag phase-N
```
The hook also allows tagging under the same handshake.

## Constraints
- Never `git push` — surface the commit hash and let the user push.
- Never `--no-verify`, `--amend` (unless user explicitly asks), or `--force`.
- Never bypass `make ci` — if it fails, fix or hand back to user.
- Never commit `.env`, `credentials.json`, `token.json`, `*.db`, or `uv.lock` (manually). The hook already denies edits to these but `git add` could stage them — verify with `git status` before staging.
- Never use the handshake outside this skill's documented procedure. It exists to make commits intentional, not to bypass safety.
