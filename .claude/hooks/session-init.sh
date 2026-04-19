#!/usr/bin/env bash
# SessionStart hook — orientation banner. Always exits 0.
set -uo pipefail

echo "=== Startup Radar — session init ==="

branch=$(git branch --show-current 2>/dev/null || echo "(not a git repo)")
echo "Branch: ${branch}"

if git rev-parse --git-dir >/dev/null 2>&1; then
  modified=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  echo "Uncommitted changes: ${modified} file(s)"
fi

if [ -d logs ] && ls logs/*.log >/dev/null 2>&1; then
  latest=$(ls -t logs/*.log 2>/dev/null | head -1)
  if [ -n "${latest}" ]; then
    age=$(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "${latest}" 2>/dev/null || stat -c '%y' "${latest}" 2>/dev/null | cut -d. -f1)
    echo "Last pipeline log: ${latest} (${age})"
  fi
else
  echo "Last pipeline log: (none)"
fi

db=""
for candidate in startup_radar.db startups.db; do
  [ -f "${candidate}" ] && db="${candidate}" && break
done
if [ -n "${db}" ] && command -v sqlite3 >/dev/null 2>&1; then
  count=$(sqlite3 "${db}" "SELECT COUNT(*) FROM startups;" 2>/dev/null || echo "?")
  echo "DB rows (startups): ${count}"
fi

echo ""
echo "Read .claude/CLAUDE.md for conventions. Refactor plan: docs/PRODUCTION_REFACTOR_PLAN.md"
exit 0
