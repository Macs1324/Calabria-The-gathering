# Calabria: The Gathering — server image.
#
# Build from the repository root:
#   docker build -t calabria-server -f server/Dockerfile .
#
# Dependency versions are locked in server/uv.lock. Keep this file and the
# flake.nix devshell in sync as the dependency set grows.

FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Runtime shared libs needed by the OpenCV wheel (headless variant needs glib et al.).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /uvx /usr/local/bin/

FROM base AS builder
WORKDIR /app
COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY server/src ./src
RUN uv sync --frozen --no-dev

FROM base AS runtime
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD [".venv/bin/uvicorn", "calabria.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
