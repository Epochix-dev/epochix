# ── Stage 1: build the Vite frontend bundle ───────────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /build/frontend

COPY frontend/package*.json ./
RUN npm ci --ignore-scripts

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Metadata
LABEL org.opencontainers.image.title="epochix server"
LABEL org.opencontainers.image.description="Visual storytelling for deep learning training runs"
LABEL org.opencontainers.image.source="https://github.com/epochix/epochix"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# System deps for WeasyPrint (pdf export) — skip if not needed by your use-case
# Uncomment the block below to enable PDF export in the container:
# RUN apt-get update && apt-get install -y --no-install-recommends \
#       libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 \
#       libffi-dev libjpeg-dev libopenjp2-7 \
#  && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd --create-home --shell /bin/bash app
WORKDIR /home/app

# Install from the local source tree (hermetic — no PyPI-propagation race with
# the release workflow, and `docker build` works from any commit, not just
# published versions). The stage-1 frontend build is placed at frontend/dist
# BEFORE `pip install .` so hatchling's force-include vendors it into the
# package exactly like the release wheel — no hand-rolled site-packages copy.
# (.dockerignore excludes the host's own frontend/dist, so the bundle used
# here always comes from the in-image build.)
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY --from=frontend-builder /build/frontend/dist/ ./frontend/dist/
RUN pip install --no-cache-dir . \
 && python -c "import epochix, pathlib; d = pathlib.Path(epochix.__file__).parent / '_frontend/dist/index.html'; assert d.is_file(), f'frontend bundle missing: {d}'" \
 && rm -rf src frontend pyproject.toml README.md LICENSE

# Data directory (SQLite DB, exports)
RUN mkdir -p /data && chown app:app /data
VOLUME ["/data"]

USER app

# Server listens on 7860 by default
EXPOSE 7860

# Health-check: /api/health is auth-exempt, so the container stays "healthy"
# even when EPOCHIX_AUTH_TOKEN is configured (unlike authenticated routes).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health')"

ENV EPOCHIX_DB=/data/runs.db \
    EPOCHIX_HOST=0.0.0.0 \
    EPOCHIX_PORT=7860

ENTRYPOINT ["epochix"]
CMD ["serve", "--host", "0.0.0.0", "--port", "7860"]
