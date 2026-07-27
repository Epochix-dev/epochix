# Configuration

Every setting is read from an environment variable prefixed `EPOCHIX_`, or from
a `.env` file in the current directory. Nothing needs configuring to start —
the defaults run entirely on your machine.

```bash
epochix config show         # the values currently in effect
```

## Settings

| Variable | Default | What it does |
|---|---|---|
| `EPOCHIX_DB` | a local SQLite file | Where runs are stored. `:memory:` keeps nothing. |
| `EPOCHIX_HOST` | `127.0.0.1` | Interface to bind. See the security note below before changing. |
| `EPOCHIX_PORT` | `7860` | Server port. |
| `EPOCHIX_LOG_LEVEL` | `INFO` | Logging verbosity. |
| `EPOCHIX_OPEN_BROWSER` | `true` | Open a browser when a run starts. |
| `EPOCHIX_KEEP_RAW_LINES` | `false` | Keep the raw log lines alongside parsed metrics. |
| `EPOCHIX_TELEMETRY` | `false` | Off. epochix sends nothing anywhere by default. |

### Serving beyond localhost

| Variable | Default | What it does |
|---|---|---|
| `EPOCHIX_AUTH_TOKEN` | empty | Required token for writes. |
| `EPOCHIX_CORS_ORIGINS` | empty | Comma-separated allowed origins. |
| `EPOCHIX_EXPOSE_DOCS` | `false` | Serve the OpenAPI docs endpoints. |
| `EPOCHIX_SCRUB_SECRETS` | `false` | Redact secret-looking strings from stored lines. |

!!! warning "Binding a public interface"

    The server treats loopback clients as trusted for writes. If you set
    `EPOCHIX_HOST` to anything other than `127.0.0.1`/`::1`/`localhost`,
    **set `EPOCHIX_AUTH_TOKEN` as well** — otherwise anyone who can reach the
    machine can create and delete runs. epochix prints a warning when you bind
    publicly without a token. See [Deployment](deployment.md).

### Optional backends

| Variable | Default | What it does |
|---|---|---|
| `EPOCHIX_REDIS_URL` | empty | Redis for the pub/sub hub across processes. |
| `EPOCHIX_POSTGRES_DSN` | empty | Postgres instead of SQLite. |

### LLM fallback parser (opt-in)

Used only when the regex parsers find no metrics at all — for example a log
written as prose. It is off unless you turn it on, and it fails open: if the
model is unreachable, the run still completes.

| Variable | Default | What it does |
|---|---|---|
| `EPOCHIX_LLM_ENABLED` | `false` | Master switch. Nothing is sent anywhere while this is off. |
| `EPOCHIX_LLM_PROVIDER` | `ollama` | Provider to use. |
| `EPOCHIX_LLM_MODEL` | `qwen2.5:7b` | Model name. |
| `EPOCHIX_OLLAMA_URL` | `http://127.0.0.1:11434` | Local Ollama endpoint. |
| `EPOCHIX_LLM_KEY` | empty | API key, for providers that need one. |

!!! note "What gets sent"

    With the fallback enabled, up to 400 cleaned log lines may be sent to the
    configured endpoint. With the default `ollama` provider that endpoint is on
    your own machine. Point it at a hosted provider and those lines leave your
    machine — check that against whatever your logs contain.

## Writing to `.env`

```bash
epochix config set port 8080
```

This writes `EPOCHIX_PORT=8080` to `.env` in the current directory.
The key is accepted with or without the `EPOCHIX_` prefix, in any case.
