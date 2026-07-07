# Deployment

epochix runs fully offline by default. This page describes options for
sharing your dashboard with teammates or deploying to a server.

---

## Local (single user, default)

```bash
epochix serve
# Dashboard at http://127.0.0.1:7860
```

The SQLite database is stored at `~/.epochix/runs.db`.

---

## Team server (LAN)

Run epochix on a machine that's accessible to your team:

```bash
epochix serve --host 0.0.0.0 --port 7860
```

Enable basic auth to prevent unauthorised access:

```bash
epochix serve --auth user:password
```

Or set via environment:

```bash
EPOCHIX_AUTH_USER=admin EPOCHIX_AUTH_PASS=secret epochix serve
```

---

## Reverse proxy (Nginx / Caddy)

### Nginx

```nginx
location /epochix/ {
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
epochix.example.com {
    reverse_proxy 127.0.0.1:7860 {
        header_up Host {host}
    }
}
```

---

## Environment variables

| Variable | Default | Description |
|--|--|--|
| `EPOCHIX_DB` | `~/.epochix/runs.db` | SQLite database path |
| `EPOCHIX_HOST` | `127.0.0.1` | Bind host |
| `EPOCHIX_PORT` | `7860` | Bind port |
| `EPOCHIX_AUTH_USER` | _(none)_ | Basic auth username |
| `EPOCHIX_AUTH_PASS` | _(none)_ | Basic auth password |
| `EPOCHIX_AUTH_TOKEN` | _(none)_ | Bearer token for API access |
| `EPOCHIX_LLM_URL` | _(none)_ | Ollama endpoint for LLM fallback |
| `EPOCHIX_LLM_KEY` | _(none)_ | OpenAI API key for LLM fallback |

---
