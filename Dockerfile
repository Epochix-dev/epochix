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
LABEL org.opencontainers.image.title="model-story server"
LABEL org.opencontainers.image.description="Visual storytelling for deep learning training runs"
LABEL org.opencontainers.image.source="https://github.com/model-story/model-story"
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

# Install the package from PyPI (or from a local wheel during CI)
# Use ARG to allow overriding the version at build time:
#   docker build --build-arg VERSION=0.1.0 .
ARG VERSION=0.1.0
RUN pip install --no-cache-dir "model-story==${VERSION}"

# Copy the pre-built frontend bundle into the expected location
COPY --from=frontend-builder /build/frontend/dist/ \
     /home/app/.local/lib/python3.12/site-packages/model_story/_frontend/dist/

# Data directory (SQLite DB, exports)
RUN mkdir -p /data && chown app:app /data
VOLUME ["/data"]

USER app

# Server listens on 7860 by default
EXPOSE 7860

# Health-check: hit the API root
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/runs')"

ENV MODEL_STORY_DB=/data/runs.db \
    MODEL_STORY_HOST=0.0.0.0 \
    MODEL_STORY_PORT=7860

ENTRYPOINT ["model-story"]
CMD ["serve", "--host", "0.0.0.0", "--port", "7860"]
