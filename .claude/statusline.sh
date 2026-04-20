#!/usr/bin/env bash
# Status line — renders: 🛰 <branch> | last run: HH:MM | <version> | ctx ▓▓░░ N% | 5h ░░░ N% | wk ░░░ N%
set -uo pipefail

input=""
if [ ! -t 0 ]; then
  input=$(cat)
fi

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

# 10-block bar; <50 green, 50-79 yellow, >=80 red.
make_bar() {
  local pct=$1
  local filled=$(( pct / 10 ))
  local empty=$(( 10 - filled ))
  local color reset="\033[0m" bar="" i=0
  if [ "$pct" -ge 80 ]; then color="\033[0;31m"
  elif [ "$pct" -ge 50 ]; then color="\033[0;33m"
  else color="\033[0;32m"
  fi
  bar="${color}"
  while [ $i -lt $filled ]; do bar="${bar}▓"; i=$(( i + 1 )); done
  i=0
  while [ $i -lt $empty ]; do bar="${bar}░"; i=$(( i + 1 )); done
  printf '%b' "${bar}${reset}"
}

meters=""
if [ -n "${input}" ] && command -v jq >/dev/null 2>&1; then
  for kv in "context_window.used_percentage:ctx" "rate_limits.five_hour.used_percentage:5h" "rate_limits.seven_day.used_percentage:wk"; do
    path="${kv%:*}"
    label="${kv#*:}"
    pct=$(echo "${input}" | jq -r ".${path} // empty" 2>/dev/null)
    if [ -n "${pct}" ]; then
      pct_int=$(printf '%.0f' "${pct}")
      bar=$(make_bar "${pct_int}")
      meters="${meters} | \033[0;35m${label}\033[0m ${bar} \033[0;35m${pct_int}%\033[0m"
    fi
  done
fi

printf "🛰 %s | last run: %s | %s%b\n" "${branch}" "${last_run}" "${version}" "${meters}"
