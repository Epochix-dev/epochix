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
| `EPOCHIX_HOST` | `127.0.0.1` | Interface the server binds, for `epochix serve` and for the server `epochix <log>` and `epochix --live` start. `serve --host` overrides it. See the security note below before changing it. |
| `EPOCHIX_PORT` | `7860` | Server port, for every command that starts one. `--port` overrides it. |
| `EPOCHIX_LOG_LEVEL` | `INFO` | Logging verbosity. |
| `EPOCHIX_OPEN_BROWSER` | `true` | Open a browser when a run starts. `false` suppresses it everywhere — every command and the Python SDK — and prints the URL instead. |
| `EPOCHIX_KEEP_RAW_LINES` | `false` | Keep the raw log lines alongside parsed metrics. |
| `EPOCHIX_SCRUB_SECRETS` | `true` | Redact secret-looking strings (API keys, tokens, passwords, credentials in URLs) from the raw lines that are stored, and from lines sent to an LLM provider. Metrics are always read from the line as printed. |
| `EPOCHIX_TELEMETRY` | `false` | Has no effect: epochix has no telemetry and sends nothing anywhere. Accepted so existing configs keep loading. |
| `EPOCHIX_GRADE_CONFIG` | empty | A grade thresholds file, a folder to look for one from (and up), or `off` for the built-in thresholds. Empty looks for the nearest `.epochix.yaml` from the current folder — see [Grade thresholds](#grade-thresholds). |

### Serving beyond localhost

| Variable | Default | What it does |
|---|---|---|
| `EPOCHIX_AUTH_TOKEN` | empty | Token required on every `/api/*` route but `/api/health` and `/api/version` (`Authorization: Bearer <token>`) and on the live feeds (`?token=<token>`). In a browser, open a dashboard page once with `?token=<token>`; see [Deployment](deployment.md#team-server-lan). |
| `EPOCHIX_CORS_ORIGINS` | empty | Comma-separated allowed origins. |
| `EPOCHIX_EXPOSE_DOCS` | `false` | Serve the OpenAPI docs endpoints. |

!!! warning "Binding a public interface"

    The server treats loopback clients as trusted for writes. If you bind
    anything other than `127.0.0.1`/`::1`/`localhost` — with `epochix serve
    --host` or with `EPOCHIX_HOST` — **set `EPOCHIX_AUTH_TOKEN` as well**;
    otherwise anyone who can reach the machine can create and delete runs.
    Every command that starts a server prints a warning, on stderr, when it
    binds publicly without a token, and the Python SDK's `epochix.serve` and
    `epochix.visualize` raise `PublicBindWarning` (a `UserWarning`, from
    `epochix.server.auth`) for a public `host=`. See
    [Deployment](deployment.md).

### Hosted backends — not built

A Redis pub/sub hub and a Postgres store are planned for a hosted mode and
do not exist yet. Earlier versions listed `EPOCHIX_REDIS_URL` and
`EPOCHIX_POSTGRES_DSN` here as working; nothing read them, so a run pointed
at Postgres went to the local SQLite file. Setting either one now stops
epochix with an error rather than storing your runs somewhere you did not
ask for.

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

## Grade thresholds

The letter grades come from built-in cut-offs. A project can replace them with
a `.epochix.yaml`:

```yaml
version: 1

grade_thresholds:
  classification:    # a task: applies to its accuracy
    "A+": 0.97
    A:    0.93
    B:    0.85
    C:    0.75
    D:    0.60
    F:    0.0
  val_f1:            # a metric: applies to it in any run
    A: 0.90
    B: 0.75
    C: 0.60
    F: 0.0
```

**Where it is looked for.** The folder epochix is run from, then each parent
folder, then `~/.epochix/.epochix.yaml`. `EPOCHIX_GRADE_CONFIG` names a file
directly, or switches the lookup off with `off`. The command line, the server
and the Python SDK read it. So does the VS Code extension, which has no folder
it is "run from": it looks from the workspace's first folder upwards, then in
`~/.epochix`. When the file is added, edited or removed, the extension reads
the open run again with the new thresholds; a run stored through its Python
server keeps the grades it was stored with, and the next run uses the file.

**What an entry is.** For each grade, the lowest value that still earns it —
or the highest, for a metric where lower is better. The order of the numbers
says which, so write them from A+ down to F. You do not have to list every
grade.

**What an entry applies to.**

| Entry | Applies to |
|---|---|
| `classification` | `val_accuracy`, `accuracy` |
| `detection` | `mAP50` |
| `segmentation` | `mIoU` |
| `nlp` | `perplexity` |
| `biometric` | `EER` |
| `gaze` | `val_MAE`, `MAE` (degrees) |
| `regression` | `val_MAE`, `MAE` |
| `generative` | `fid` |
| `custom` | whatever a run with no recognised task is told by |
| a metric's name, such as `val_f1` or `R2` | that metric, in any run |

A task's entry is not applied to the task's other metrics: thresholds written
for accuracy mean nothing for an AUC. Name the metric to set bands for it.

A `regression`, `generative` or `custom` entry does more than move cut-offs.
Those runs are graded on how far the metric improved, because a log cannot say
what a good MAE is; your entry supplies that, and the run is graded on it
instead.

**Checking it.** `epochix check train.log` prints the file in use and whether
an entry applies to that log, and reports anything in the file it could not
use — an unknown grade, a threshold that is not a number, or thresholds that
are not in order.

[`.epochix.example.yaml`](https://github.com/epochix-dev/epochix/blob/main/.epochix.example.yaml)
lists every entry with the built-in values, commented out.

## Writing to `.env`

```bash
epochix config set db ./runs.db
```

This writes `EPOCHIX_DB=./runs.db` to `.env` in the current directory.
The key is accepted with or without the `EPOCHIX_` prefix, in any case.
An existing line for the setting is replaced, however it is written.

A key that is not one of the settings above, or a value the setting cannot
take (`config set port abc`), is refused and nothing is written.

The rest of the `.env` is left alone. It is usually your project's own, and
keys epochix does not use (`OPENAI_API_KEY`, `DATABASE_URL`) are ignored. An
`EPOCHIX_*` name epochix does not use is ignored too, in the file as in the
environment. A setting with a value it cannot take stops every command with
one line naming it.

`config show` prints `auth_token` and `llm_key` as `(set, hidden)`, so its
output can go into a bug report.
