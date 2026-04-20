---
name: data-branch-bootstrap
description: One-time creation of the orphan `data` branch on origin, used by GH Actions to persist the SQLite DB across runs. Sanctioned exception to the "no git push" rule via STARTUP_RADAR_DATA_BOOTSTRAP=1 handshake.
when_to_use: When the user says "bootstrap data branch", "/data-branch-bootstrap", "set up GH Actions persistence", or after a fresh fork / clone. NEVER auto-invoke. NEVER run if `git ls-remote --heads origin data` already returns a ref.
allowed-tools: [Bash]
---

# /data-branch-bootstrap — orphan data-branch creation

Wraps the 6-command bootstrap from `docs/operations/data-branch.md`. Pushes via the `STARTUP_RADAR_DATA_BOOTSTRAP=1` handshake — the only sanctioned path for Claude to push a new branch in this repo.

## Procedure

### 1. Pre-flight (STOP on any failure)

Run in parallel:

```bash
git status --porcelain
git branch --show-current
git ls-remote --heads origin data
```

- **`git status --porcelain` non-empty** → STOP. Tell the user to commit or stash before bootstrapping; the orphan checkout will refuse to overwrite uncommitted changes.
- **`git ls-remote --heads origin data` returns a ref** → STOP. The branch already exists; running this skill would clobber it with a fresh orphan. If the user truly wants to reset, that's a separate destructive operation requiring explicit confirmation and a different procedure (not this skill).
- **`git branch --show-current`** → save the value as `ORIG_BRANCH`. We return to it at the end.

### 2. Confirm with the user

Print exactly what will happen:

> I'm about to:
> 1. Create an orphan branch `data` (no shared history with main).
> 2. Strip the index and add a 1-line README.md.
> 3. Commit + push to `origin data`.
> 4. Return you to `<ORIG_BRANCH>`.
>
> This is a one-shot setup for GH Actions DB persistence. Proceed? (yes / cancel)

If anything other than "yes", STOP.

### 3. Bootstrap (orphan + commit + push)

The push uses the handshake; nothing else does.

```bash
git checkout --orphan data
git rm -rf .
printf '# startup-radar data branch\n' > README.md
git add README.md
git commit -m "chore(data): initialize orphan data branch"
STARTUP_RADAR_DATA_BOOTSTRAP=1 git push origin data
```

If the push fails (network, perms), surface the error verbatim and proceed to step 5 (return to original branch) — leave the local `data` branch in place so the user can retry.

### 4. Return to the original branch

```bash
git checkout "${ORIG_BRANCH}"
```

### 5. Verify

```bash
git ls-remote --heads origin data
```

Expect one ref. Tell the user: "data branch ready; the next `daily.yml` run will commit your DB to it."

### 6. Tell the user the second human step

The skill cannot do this — it's a GitHub UI setting:

> One more thing you have to do yourself, in the GitHub web UI:
> **Settings → Actions → General → Workflow permissions → "Read and write permissions" → Save.**
>
> Without this, the daily workflow won't be able to push to the `data` branch.

## Constraints

- The handshake `STARTUP_RADAR_DATA_BOOTSTRAP=1` MUST be on the same command line as `git push`, with no other commands between them. The hook checks the literal command string.
- Only push to `origin data`. Never push to other refs under this handshake.
- Never use this skill to reset / re-bootstrap an existing `data` branch — that's destructive and out of scope.
- Never run without explicit user confirmation in step 2.
- If anything goes wrong mid-procedure, ALWAYS return to the original branch in step 4 before reporting back.
