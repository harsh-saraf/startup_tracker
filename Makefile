.PHONY: help install install-dev test lint format format-check typecheck ci serve run doctor clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Sync runtime + dev deps via uv (lockfile -> .venv)
	uv sync --all-extras

install-dev: install  ## Alias for install (dev deps included by default)

test:  ## Run pytest
	uv run pytest

lint:  ## Run ruff check
	uv run ruff check .

format:  ## Auto-format with ruff
	uv run ruff format .

format-check:  ## Check formatting without writing
	uv run ruff format --check .

typecheck:  ## Run mypy on typed modules
	uv run mypy

ci: lint format-check typecheck test  ## Full local CI: lint + format + typecheck + test

serve:  ## Start the Streamlit dashboard
	uv run startup-radar serve

run:  ## Run the discovery pipeline once
	uv run startup-radar run

doctor:  ## Quick environment check (Phase 4 will replace with `startup-radar doctor`)
	@uv run python --version
	@test -f config.yaml && echo "config.yaml: ok" || echo "config.yaml: MISSING (copy from config.example.yaml)"
	@test -f startup_radar.db && echo "DB exists" || echo "DB not yet created"

clean:  ## Remove build/cache artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
