# Deployment

model-story runs fully offline by default. This page describes options for
sharing your dashboard with teammates or deploying to a server.

---

## Local (single user, default)

```bash
model-story serve
# Dashboard at http://127.0.0.1:7860
```

The SQLite database is stored at `~/.model-story/model_story.db`.

---

## Team server (LAN)

Run model-story on a machine that's accessible to your team:

```bash
model-story serve --host 0.0.0.0 --port 7860
```

Enable basic auth to prevent unauthorised access:

```bash
model-story serve --auth user:password
```

Or set via environment:

```bash
MODEL_STORY_AUTH_USER=admin MODEL_STORY_AUTH_PASS=secret model-story serve
```

---

## Docker

```bash
docker run -p 7860:7860 \
  -v ~/.model-story:/data \
  ghcr.io/model-story/server:latest
```

With docker-compose:

```yaml
version: "3.9"
services:
  model-story:
    image: ghcr.io/model-story/server:latest
    ports:
      - "7860:7860"
    volumes:
      - model-story-data:/data
    environment:
      MODEL_STORY_DB: /data/model_story.db

volumes:
  model-story-data:
```

---

## Reverse proxy (Nginx / Caddy)

### Nginx

```nginx
location /model-story/ {
    proxy_pass         http://127.0.0.1:7860/;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade $http_upgrade;
    proxy_set_header   Connection "upgrade";  # required for WebSocket
    proxy_set_header   Host $host;
    proxy_read_timeout 86400;
}
```

### Caddy

```caddy
model-story.example.com {
    reverse_proxy 127.0.0.1:7860 {
        header_up Host {host}
    }
}
```

---

## Environment variables

| Variable | Default | Description |
|--|--|--|
| `MODEL_STORY_DB` | `~/.model-story/model_story.db` | SQLite database path |
| `MODEL_STORY_HOST` | `127.0.0.1` | Bind host |
| `MODEL_STORY_PORT` | `7860` | Bind port |
| `MODEL_STORY_AUTH_USER` | _(none)_ | Basic auth username |
| `MODEL_STORY_AUTH_PASS` | _(none)_ | Basic auth password |
| `MODEL_STORY_AUTH_TOKEN` | _(none)_ | Bearer token for API access |
| `MODEL_STORY_LLM_URL` | _(none)_ | Ollama endpoint for LLM fallback |
| `MODEL_STORY_LLM_KEY` | _(none)_ | OpenAI API key for LLM fallback |

---

## Hosted version (v0.2+)

A hosted version with shareable permalinks and team workspaces is planned
for v0.2. See the [roadmap](https://github.com/model-story/model-story/blob/main/ARCHITECTURE.md#24-roadmap--milestones).
