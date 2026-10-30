# Calabria: The Gathering — server image (API + built web client).
#
# Build from the repository root:
#   docker build -t calabria -f server/Dockerfile .
# Build the card index once into a volume, then serve:
#   docker run --rm -v calabria-data:/data calabria calabria-build-index --data-dir /data
#   docker run -d -p 8000:8000 -v calabria-data:/data calabria
#
# Dependency versions are locked in server/uv.lock and app/pnpm-lock.yaml.
# Keep this file and the flake.nix devshell in sync as the dependency set grows.

FROM node:22-slim AS web
WORKDIR /web
RUN npm install -g pnpm@12.9.0
COPY app/package.json app/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY app/index.html app/vite.config.ts app/tsconfig.json app/tsconfig.node.json ./
COPY app/public ./public
COPY app/src ./src
RUN pnpm build

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
COPY --from=web /web/dist /app/web
# Card index + room logs live in /data: mount a volume so both survive upgrades.
ENV PATH="/app/.venv/bin:$PATH" \
    CALABRIA_DATA_DIR=/data \
    CALABRIA_WEB_DIR=/app/web
VOLUME /data
EXPOSE 8000
CMD [".venv/bin/uvicorn", "calabria.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
