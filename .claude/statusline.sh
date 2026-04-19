#!/usr/bin/env bash
# Status line — renders: 🛰 <branch> | last run: HH:MM | <version>
set -uo pipefail

branch=$(git branch --show-current 2>/dev/null || echo "?")

last_run="—"
if [ -d logs ] && ls logs/*.log >/dev/null 2>&1; then
  latest=$(ls -t logs/*.log 2>/dev/null | head -1)
  if [ -n "${latest}" ]; then
    last_run=$(stat -f '%Sm' -t '%H:%M' "${latest}" 2>/dev/null || stat -c '%y' "${latest}" 2>/dev/null | cut -d' ' -f2 | cut -d: -f1-2)
  fi
fi

version=""
if [ -f pyproject.toml ]; then
  version=$(grep -E '^version\s*=' pyproject.toml | head -1 | sed -E 's/.*"([^"]+)".*/\1/' || echo "")
fi
[ -z "${version}" ] && version="dev"

echo "🛰 ${branch} | last run: ${last_run} | ${version}"
