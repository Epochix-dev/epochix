# CLI reference

Every command below is real and current — run `epochix <command> --help` for the
full option list, which is generated from the code itself.

If the dashboard looks empty or the grade looks wrong, start with
[`epochix check`](#epochix-check). It reports what the parsers can and cannot
read from your log and tells you what to add.

---

## `epochix run`

Parse a training log and visualise it. This is the default action, so
`epochix train.log` and `epochix run train.log` are the same thing.

```bash
epochix run train.log
```

Useful options:

| Option | What it does |
|---|---|
| `--headless` | Do not open a browser. Use in CI. |
| `--export html\|pdf\|md\|json` | Write a report (requires `--headless`). |
| `--output`, `-o` | Where to write that report. Parent directories are created. Defaults to `<run_id>.<format>` in the current directory. |
| `--port`, `-p` | Server port (default `7860`). |
| `--task`, `-t` | Force the task type instead of detecting it. |
| `--name`, `-n` | Give the run a readable name. |
| `--no-llm` | Disable the optional LLM fallback parser. |

Watch a run as it trains by piping into epochix. Piped input is detected
automatically, and `--live` forces it:

```bash
python train.py | epochix
python train.py | epochix --live
```

To follow a file that is still being written, or a log on another machine, see
`--tail` and `--ssh` in `epochix run --help`.

## `epochix demo`

See the dashboard without training anything of your own.

```bash
epochix demo
epochix demo yolov8
```

## `epochix check`

Explain what epochix can read from a log — and what to add so it can read more.
Nothing is stored and nothing is served; this only reports.

```bash
epochix check train.log
```

Reach for this first when a run produced no story, an unexpected grade, or an
empty architecture panel.

## `epochix serve`

Start the server on its own, without processing a run.

```bash
epochix serve --port 7860
```

If the port is taken, epochix says so and suggests another rather than raising
a traceback. Binding a non-loopback `--host` without `EPOCHIX_AUTH_TOKEN`
prints a warning — see [Configuration](config.md).

## `epochix list`

List saved runs, newest first.

## `epochix open`

Open a saved run in the browser by run ID.

## `epochix export`

Export a saved run as HTML, PDF, Markdown, or JSON.

```bash
epochix export <run_id> --format md --output report.md
```

PDF needs the extra: `pip install 'epochix[pdf]'`.

## `epochix prune`

Delete runs older than a given age. Check first with `--dry-run`:

```bash
epochix prune --older-than 30d --dry-run
```

## `epochix config`

Show or set configuration values. See [Configuration](config.md).

```bash
epochix config show
epochix config set port 8080
```
