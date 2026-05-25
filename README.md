# Model Learning Story

> Visual storytelling for deep learning training runs.

[![PyPI version](https://img.shields.io/pypi/v/model-story.svg?color=blue)](https://pypi.org/project/model-story/)
[![Python](https://img.shields.io/pypi/pyversions/model-story.svg)](https://pypi.org/project/model-story/)
[![CI](https://github.com/model-story/model-story/actions/workflows/ci.yml/badge.svg)](https://github.com/model-story/model-story/actions/workflows/ci.yml)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/model-story.model-story?label=VS%20Code)](https://marketplace.visualstudio.com/items?itemName=model-story.model-story)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

**Turn terminal training logs into an animated, plain-English narrative anyone can understand.**

```
Epoch 7/20  ████████████░░░░  train_loss: 0.312  val_accuracy: 0.847
```
↓
```
⚡ Mastering phase — Grade B+

The model reaches a significant milestone at epoch 7. Val accuracy 84.7%
(Δ +3.1%) — the network has stopped memorising and started generalising.
```

---

## Install

```bash
pip install model-story
```

Optional extras:

```bash
pip install "model-story[pdf]"       # PDF export via WeasyPrint
pip install "model-story[lightning]" # PyTorch Lightning callback
pip install "model-story[hf]"        # HuggingFace Trainer callback
pip install "model-story[all]"       # everything above
```

---

## Quick start

### One-liner: pipe any training log

```bash
python train.py 2>&1 | model-story --live
```

### Parse a saved log file

```bash
model-story batch training.log
```

### Start the local dashboard server

```bash
model-story serve
# → opens http://127.0.0.1:7860 in your browser
```

### Python SDK

```python
from model_story import parse, LiveReporter

# Parse a finished log
result = parse("training.log")
print(result.final_grade, result.summary)

# Stream live during training (PyTorch Lightning)
from model_story.integrations.lightning import ModelStoryCallback

trainer = pl.Trainer(callbacks=[ModelStoryCallback()])
```

### Docker

```bash
docker run -p 7860:7860 ghcr.io/model-story/server:latest
```

---

## Features

| | |
|---|---|
| **7 log parsers** | PyTorch Lightning · Keras/TF · HuggingFace · YOLO · FastAI · Accelerate · Universal |
| **7 task types** | Classification · Detection · Regression · Biometric · Gaze · NLP · Generative |
| **5 training phases** | Awakening → Learning → Understanding → Mastering → Polishing |
| **11 letter grades** | A+ through F, task-specific thresholds, configurable via `.model-story.yaml` |
| **Live streaming** | WebSocket + SSE with ring-buffer replay on reconnect |
| **Exports** | JSON · Markdown · HTML (self-contained < 2 MB) · PDF |
| **i18n** | English · Farsi (RTL) · French |
| **VS Code** | Sidebar dashboard · terminal watcher · `Ctrl+Alt+M` |
| **Integrations** | PyTorch Lightning · HuggingFace · Keras · Jupyter magics · TensorBoard · W&B |
| **Plugin system** | Custom parsers, metaphor packs, task types, exporters via `entry_points` |

---

## Security & deployment

model-story is **local-first**: by default the server binds to `127.0.0.1`, requires
no token, and allows any origin — convenient and safe on your own machine.

If you expose it beyond localhost (a shared box, a container, the internet), turn on
authentication and lock down CORS:

```bash
# Require a token on every request, and only allow your own origin
export MODEL_STORY_AUTH_TOKEN="$(openssl rand -hex 24)"
export MODEL_STORY_CORS_ORIGINS="https://story.example.com"
model-story serve --host 0.0.0.0 --port 7860
```

| Setting | Env var | Default | Effect |
|---|---|---|---|
| Auth token | `MODEL_STORY_AUTH_TOKEN` | _(empty — open)_ | Require a token on all routes |
| CORS origins | `MODEL_STORY_CORS_ORIGINS` | `*` | Comma-separated allowlist |

How the token is checked:

- **REST** (`/api/*`): send `Authorization: Bearer <token>`.
- **WebSocket / SSE** (`/ws/live/...`, `/sse/live/...`): pass `?token=<token>` in the URL
  (browsers can't set headers on those transports). Without it, live streams are refused.

> **Note:** wildcard CORS (`*`) and credentialed requests are never combined — credentials
> are enabled only when you set explicit origins. And when a token is configured, the
> **bundled dashboard** has no way to supply it, so live updates won't load from the served
> page. For authenticated hosting, put model-story behind a reverse proxy (nginx, Caddy,
> Cloudflare Access, …) that handles auth and serves the UI.

Settings can also be written to a local `.env`:

```bash
model-story config set auth_token "$(openssl rand -hex 24)"
model-story config show
```

---

## Custom grade thresholds

Place a `.model-story.yaml` in your project root:

```yaml
version: 1

grade_thresholds:
  classification:
    "A+": 0.97   # tighter standard for your domain
    A:    0.93
    # ... (see .model-story.yaml template for all grades)

lower_better:
  nlp: true      # perplexity
```

---

## VS Code Extension

Install from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=model-story.model-story)
or search **"Model Learning Story"** in the Extensions panel.

- Open the **Model Story Runs** tree view in the Explorer sidebar
- Press `Ctrl+Alt+M` (`Cmd+Alt+M` on macOS) to open the dashboard panel
- Works in standalone mode (no Python required) or sidecar mode with the Python package

---

## Claude Artifact

Copy the content of `src/model_story/_artifacts/model-story.artifact.jsx` into a Claude
conversation artifact to get a fully interactive training story viewer — no server, no install.

---

## Documentation

Full docs at **[docs.model-story.dev](https://docs.model-story.dev)**

- [Getting started](https://docs.model-story.dev/getting-started/)
- [CLI reference](https://docs.model-story.dev/cli/)
- [Python SDK](https://docs.model-story.dev/sdk/)
- [Plugin system](https://docs.model-story.dev/plugins/)
- [Configuration](https://docs.model-story.dev/config/)

---

## Contributing

```bash
git clone https://github.com/model-story/model-story
cd model-story
pip install -e ".[dev]"
pytest tests/unit tests/integration
```

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

---

## License

[Apache 2.0](LICENSE) — © 2026 HexoraX
