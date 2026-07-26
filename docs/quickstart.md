# Quickstart

Get a live dashboard for your training run in under 60 seconds.

---

## 0. Easiest: the VS Code extension (no Python needed)

1. Install [**Epochix** from the Marketplace](https://marketplace.visualstudio.com/items?itemName=epochix.epochix).
2. Click the **E** icon in the left sidebar → **▶ Try a Demo Run** — an
   animated dashboard opens on a bundled training run.
3. Run your own training in the integrated terminal — the dashboard opens by
   itself the moment Epochix recognises training output.

That's the whole flow. The steps below add the Python package, which the
extension uses automatically for run history, comparison and exports.

---

## 1. Install

```bash
pip install epochix
```

---

## 2. Pipe your training script

```bash
python train.py 2>&1 | epochix --live
```

Your browser opens automatically. The dashboard updates in real time.

---

## 3. Parse an existing log file

```bash
epochix train.log
```

---

## Common patterns

### PyTorch Lightning

```python
from epochix.integrations.lightning import StoryCallback
import lightning as pl

trainer = pl.Trainer(callbacks=[StoryCallback()])
trainer.fit(model, datamodule=dm)
```

### HuggingFace Trainer

```python
from epochix.integrations.hf import StoryCallback
from transformers import Trainer, TrainingArguments

trainer = Trainer(
    model=model,
    args=TrainingArguments(...),
    callbacks=[StoryCallback(primary_metric="eval_f1")],
)
trainer.train()
```

### Jupyter / Colab

```python
%load_ext epochix

# Parse a finished log:
%epochix train.log

# Live mode — runs the next cell through epochix:
%%epochix --live
!python train.py
```

### Python SDK

```python
from epochix.sdk import LiveReporter

with LiveReporter(task="classification") as reporter:
    for epoch in range(50):
        # ... your training loop ...
        reporter.log(train_loss=loss.item(), val_accuracy=acc)
```

Pass `model=` to draw the **real** architecture in the Network State panel, and
add `capture_activations=True` to drive the panel's node brightness and dead
nodes from **real** per-layer activation magnitudes captured live during
training (mean `|activation|`, zero-unit fraction, and — via backward hooks —
gradient magnitude). It's opt-in and wall-clock throttled (`activation_hz`,
2 Hz default), so overhead is negligible:

```python
with LiveReporter(
    task="gaze",
    model=model,                  # real layer names / types / params
    capture_activations=True,     # real node activity (default off)
    activation_hz=2.0,            # sampling cap; .item() forces a GPU sync
) as reporter:
    for epoch in range(50):
        # ... train (model.train()) ...
        reporter.log(train_loss=tr_loss, val_loss=va_loss, val_mae_cm=mae)
```

---

## CLI reference

```
epochix --help
```

| Command | Description |
|--|--|
| `epochix <file>` | Parse a finished log file |
| `epochix check <file>` | Say what epochix can read from a log — and what to add |
| `epochix --live` | Pipe stdin in live mode |
| `epochix serve` | Start the dashboard server only |
| `epochix list` | List all saved runs |
| `epochix export <id> --format html` | Export a run |
| `epochix compare <id1> <id2>` | Side-by-side run comparison |
| `epochix prune --older-than 30d` | Delete old runs |

---

## Dashboard looks empty or the grade looks wrong?

Ask epochix what it can see:

```bash
epochix check train.log
```

It reports which parser matched, which metrics it found (and their range), the
task it inferred, and — the useful part — exactly what's missing:

```
  parser        universal
  task          custom
  epochs seen   5

  metrics found
    train_loss          5 values   0.4 -> 0.28
    val_loss            5 values   0.207 -> 0.187

  to improve this run
    ! No task-defining metric (accuracy / mAP / F1 / MAE / perplexity ...),
      so the run is graded on how much its loss improved rather than on
      task quality. Log one to get a real grade, e.g.
        print(f"Epoch {epoch}/{total} train_loss={loss:.4f} val_accuracy={acc:.4f}")
    ! No model architecture - the Network panel will stay empty.
      Either print the model summary once at the start ...
```

**Writing your own training loop?** One `print` per epoch is all epochix needs:

```python
print(f"Epoch {epoch}/{total} train_loss={loss:.4f} val_accuracy={acc:.4f}", flush=True)
```

Include the epoch (`Epoch 3/20` or `epoch=3`) so the progress bar advances, and
print your model summary once at the start (Keras `model.summary()`, torchinfo,
or plain `print(model)`) to fill the Network panel.

---

## LLM fallback for unknown log formats (opt-in)

If none of the built-in parsers recognise your log format, epochix can ask a
local Ollama (or OpenAI) to extract the metrics. It is off by default, fires
only at end of stream, and only when the regex parsers found **nothing** — a
normal run never touches it.

```bash
EPOCHIX_LLM_ENABLED=true EPOCHIX_LLM_MODEL=qwen2.5:7b epochix weird.log
```

- **Ollama** (default provider): talks to `EPOCHIX_OLLAMA_URL`
  (default `http://127.0.0.1:11434`).
- **OpenAI**: set `EPOCHIX_LLM_PROVIDER=openai` and `EPOCHIX_LLM_KEY=sk-…`.
- `--no-llm` disables it for a single run.
- LLM-extracted metrics are marked with lower confidence than regex parses,
  and non-numeric or non-finite hallucinations are dropped.

---

## Remote & reverse-proxy deployment

`epochix serve` is a single-origin app; it works well behind a TLS-terminating
reverse proxy **as long as the app is served at the root of its origin** (a
dedicated host/subdomain), because the dashboard references assets, the API and
the WebSocket with absolute-from-root paths (`/assets`, `/api`, `/ws/live`).

- **Bind address**: `epochix serve --host 0.0.0.0 --port 7860` to accept
  non-localhost connections (only do this on a trusted network or behind a
  proxy).
- **TLS**: terminate HTTPS at the proxy. The dashboard detects `https://` and
  automatically upgrades the live feed to `wss://` — no config needed.
- **WebSocket**: the proxy must forward the WebSocket upgrade for `/ws/live/*`
  (e.g. nginx `proxy_set_header Upgrade $http_upgrade; proxy_set_header
  Connection "upgrade";`). If WebSockets are blocked, the dashboard falls back
  to SSE at `/sse/*`.
- **Auth**: set `EPOCHIX_AUTH_TOKEN` to require `?token=<token>` on the WS/SSE
  feed and to reveal the API docs at `/api/docs`; leave it unset for
  localhost-only use.
- **CORS**: `EPOCHIX_CORS_ORIGINS` (comma-separated) opts into cross-origin API
  access; the default is same-origin only.

**Not supported:** serving under a URL sub-path (e.g. `https://host/epochix/`).
The dashboard assumes it lives at the origin root — proxy it at the root of a
(sub)domain instead.

---

## Next steps

- [Supported frameworks](parsers.md) — see all supported log formats
- [Deployment](deployment.md) — share with your team
- [Plugins](plugins.md) — add support for custom frameworks
