.PHONY: help install install-dev test test-unit test-integration test-record lint format format-check typecheck ci serve run doctor db-migrate clean docker-build docker-run docker-shell docs docs-serve

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Sync runtime + dev deps via uv (lockfile -> .venv)
	uv sync --all-extras

install-dev: install  ## Alias for install (dev deps included by default)

test:  ## Run pytest
	uv run pytest

test-unit:  ## Run only fast unit tests (no cassettes)
	uv run pytest tests/unit/

test-integration:  ## Run only cassette-backed source tests
	uv run pytest tests/integration/

test-record:  ## Re-record all cassettes (deletes existing, hits network)
	@read -p "This deletes all cassettes and hits the network. Continue? [y/N] " ok && [ "$$ok" = "y" ] || exit 1
	rm -rf tests/fixtures/cassettes/*/
	uv run pytest tests/integration/

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

db-migrate:  ## Apply pending SQLite migrations (safe to re-run; idempotent)
	uv run python -c "from startup_radar.config import load_config; from startup_radar.storage import load_storage; s = load_storage(load_config()); print(f'user_version={s.user_version()}'); s.close()"

clean:  ## Remove build/cache artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

docker-build:  ## Build the single-image container (startup-radar:phase-14)
	docker build -t startup-radar:phase-14 .

docker-run:  ## Run the dashboard in a container (mounts ./data + ./config)
	docker run --rm -p 8501:8501 -v $$PWD/data:/data -v $$PWD/config:/config startup-radar:phase-14

docker-shell:  ## Open a bash shell inside the container for inspection
	docker run --rm -it --entrypoint bash -v $$PWD/data:/data -v $$PWD/config:/config startup-radar:phase-14

docs:  ## Build the MkDocs site into ./site with --strict
	uv run mkdocs build --strict

docs-serve:  ## Live-reload the MkDocs site on :8000
	uv run mkdocs serve
