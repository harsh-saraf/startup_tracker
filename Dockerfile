# syntax=docker/dockerfile:1.7
# --- builder: resolve the uv.lock'd graph into /app/.venv ---------------------
FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY startup_radar/ ./startup_radar/

RUN uv sync --frozen --all-extras --no-dev

# --- runtime: slim image with just the venv + package source -----------------
FROM python:3.11-slim AS runtime

RUN groupadd -g 10001 radar && useradd -u 10001 -g 10001 -m -d /home/radar radar

WORKDIR /app

COPY --from=builder --chown=10001:10001 /app /app
COPY --chown=10001:10001 config.example.yaml ./

RUN mkdir -p /data /config && chown 10001:10001 /data /config

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001:10001

VOLUME ["/data", "/config"]
EXPOSE 8501

ENTRYPOINT ["startup-radar"]
CMD ["--config", "/config/config.yaml", "serve", "--port", "8501", "--address", "0.0.0.0"]
