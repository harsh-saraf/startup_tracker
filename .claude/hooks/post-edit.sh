#!/usr/bin/env bash
# PostToolUse(Edit|Write) hook — sync ruff format on the changed Python file only.
# Always exits 0; formatter failures are non-blocking warnings.
set -uo pipefail

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

file=$(jq -r '.tool_input.file_path // .tool_input.filePath // empty' 2>/dev/null)
if [ -z "${file}" ] || [ "${file}" = "null" ]; then
  exit 0
fi

# Python files only
case "${file}" in
  *.py) ;;
  *) exit 0 ;;
esac

# Skip generated/vendored
case "${file}" in
  *.venv/*|*venv/*|*site-packages/*|*__pycache__/*) exit 0 ;;
esac

# Sync format — sub-second on a single file.
if command -v ruff >/dev/null 2>&1; then
  ruff format --quiet "${file}" 2>/dev/null || true
  ruff check --fix --quiet "${file}" 2>/dev/null || true
elif command -v uvx >/dev/null 2>&1; then
  uvx ruff format --quiet "${file}" 2>/dev/null || true
  uvx ruff check --fix --quiet "${file}" 2>/dev/null || true
fi

exit 0
