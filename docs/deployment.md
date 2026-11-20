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

Proxy epochix at the **root of its own host** (a dedicated domain or
subdomain, such as `epochix.example.com`). Serving it under a sub-path such
as `https://example.com/epochix/` does not work: the dashboard requests its
assets, the API and the live feeds from the root of the origin (`/assets`,
`/api`, `/ws/live`, `/sse/live`), outside the proxied path, so the page
arrives without its scripts or any run.

Forward the client's address in `X-Forwarded-For`. epochix trusts that
header from a proxy on the same machine, and when no `EPOCHIX_AUTH_TOKEN` is
set it accepts writes only from loopback clients. A proxy that leaves the
header out makes every visitor look like a same-machine caller, so anyone who
can reach the proxy can create and delete runs. Set `EPOCHIX_AUTH_TOKEN` as
well for anything reachable from outside.

### Nginx

```nginx
# `Connection: upgrade` for WebSocket requests only.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name epochix.example.com;
    # ssl_certificate / ssl_certificate_key ...

    location / {
        proxy_pass         http://127.0.0.1:7860;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;          # /ws/live
        proxy_set_header   Connection $connection_upgrade;
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

`/sse/live` responses carry `X-Accel-Buffering: no`, so nginx passes them on
as they are sent without `proxy_buffering off`. Both live feeds send a
heartbeat every 15 seconds, well inside nginx's default 60-second
`proxy_read_timeout`.

### Caddy

```caddy
epochix.example.com {
    reverse_proxy 127.0.0.1:7860
}
```

Caddy gets a certificate for the host, forwards the WebSocket upgrade and
sets `X-Forwarded-For` by default.

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
