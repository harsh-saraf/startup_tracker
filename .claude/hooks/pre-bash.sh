#!/usr/bin/env bash
# PreToolUse(Bash) hook — defense-in-depth block of dangerous commands.
# exit 2 = block (stderr surfaced to Claude). exit 0 = allow.
set -uo pipefail

if ! command -v jq >/dev/null 2>&1; then
  exit 0  # Degrade gracefully if jq missing
fi

cmd=$(jq -r '.tool_input.command // ""' 2>/dev/null)
if [ -z "${cmd}" ]; then
  exit 0
fi

# Sanctioned-commit handshake: the /ship skill prefixes its commits with
# STARTUP_RADAR_SHIP=1. Bare `git commit` is still denied below.
if echo "${cmd}" | grep -qE '(^|&&\s*|;\s*)STARTUP_RADAR_SHIP=1\s+git\s+(commit|tag)\b'; then
  exit 0
fi

# Sanctioned data-branch-bootstrap handshake: the /data-branch-bootstrap skill
# prefixes its push with STARTUP_RADAR_DATA_BOOTSTRAP=1. Only `git push origin data`
# (with optional --set-upstream) is allowed under this handshake — no other refs,
# no force flag. Bare `git push` is still subject to the deny rules below.
if echo "${cmd}" | grep -qE '(^|&&\s*|;\s*)STARTUP_RADAR_DATA_BOOTSTRAP=1\s+git\s+push(\s+--set-upstream)?\s+origin\s+data(\s|$)'; then
  exit 0
fi

# Pattern + reason as separate args. Use a function to keep | available for regex alternation.
check() {
  local pattern="$1"
  local reason="$2"
  if echo "${cmd}" | grep -qE "${pattern}"; then
    echo "BLOCKED by .claude/hooks/pre-bash.sh: ${reason}" >&2
    echo "  Command: ${cmd}" >&2
    echo "  (For commits, use the /ship skill which sets STARTUP_RADAR_SHIP=1.)" >&2
    exit 2
  fi
}

check 'rm -rf (/|~|\$HOME|\*|\.\*)'        'Refusing destructive recursive delete.'
check 'rm -rf /tmp'                        'Refusing to wipe /tmp.'
check 'sudo '                              'No sudo. Ask the user to run privileged commands.'
check 'chmod 777'                          'Refusing world-writable chmod.'
check 'curl .* \| (sh|bash)'               'Refusing curl pipe-to-shell.'
check 'wget .* \| (sh|bash)'               'Refusing wget pipe-to-shell.'
check 'git push.*--force'                  'Refusing force push.'
check 'git push.*-f( |$)'                  'Refusing force push (-f).'
check 'git push.* (main|master)'           'Refusing direct push to main/master.'
check 'git reset --hard'                   'Refusing destructive reset.'
check 'git config '                        'Refusing to mutate git config.'
check 'git commit '                        'Refusing to commit. Surface the diff and let the user commit.'
check 'cat .*\.env'                        'Refusing to read .env files.'
check 'cat .*credentials'                  'Refusing to read credentials files.'
check 'cat .*token\.json'                  'Refusing to read token.json.'
check 'pip install'                        'Use `make install` or `uv add` — never raw pip install.'
check 'pip3 install'                       'Use `make install` or `uv add`.'

exit 0
