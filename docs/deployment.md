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

Set an access token to keep anyone else on the network out:

```bash
export EPOCHIX_AUTH_TOKEN="$(openssl rand -hex 24)"
epochix serve --host 0.0.0.0 --port 7860
```

Then every `/api/*` route except `/api/health` and `/api/version` wants
`Authorization: Bearer <token>`, and the live feeds (`/ws/live/...`,
`/sse/live/...`) want `?token=<token>`. Writes want the token too, even from
the same machine.

To open the dashboard, add the token to any page's address once:
`http://<host>:7860/?token=<token>`, or `http://<host>:7860/v/<run>?token=<token>`.
The page takes `?token=` out of the address bar straight away, keeps it for
that tab until the tab is closed, and sends it on every request it makes — the
Bearer header to the API, `?token=` on the live feed. Following links in the
tab needs nothing more; a tab opened afresh needs `?token=` again. No link on
the page carries the token and no exported report contains it. It is in the
URL of that first page load and of each live-feed request, so it shows up in
the server's access log (and a proxy's) — on anything but a trusted LAN, serve
over HTTPS and keep those logs private. Opened without the token, the page says
it needs one.

There is no username/password login: earlier versions of this page described
`epochix serve --auth user:password` and `EPOCHIX_AUTH_USER`/`EPOCHIX_AUTH_PASS`,
which nothing reads.

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
| `EPOCHIX_HOST` | `127.0.0.1` | Interface the server binds, for `epochix serve` and for the server `epochix <log>`, `epochix --live` and `epochix open` start. `serve --host` overrides it. |
| `EPOCHIX_PORT` | `7860` | Server port, for every command that starts one. `--port` overrides it. |
| `EPOCHIX_AUTH_TOKEN` | _(none)_ | Access token for the API and the live feeds — see [Team server](#team-server-lan) |
| `EPOCHIX_LLM_URL` | _(none)_ | Ollama endpoint for LLM fallback |
| `EPOCHIX_LLM_KEY` | _(none)_ | OpenAI API key for LLM fallback |

---
