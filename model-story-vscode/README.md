# Model Learning Story for VS Code

> Turn terminal training logs into an animated, plain-English narrative —
> live in your editor.

![Phase](https://img.shields.io/badge/Phase-Awakening→Polishing-7c6dff)
![License](https://img.shields.io/badge/License-Apache--2.0-green)

A live dashboard for deep-learning training runs. Drop in a training log
(YOLO, PyTorch Lightning, Keras, HuggingFace, FastAI, …) and watch the
metrics, the architecture, the phase journey, and a plain-English narrative
all update epoch-by-epoch — without ever leaving the editor.

---

## What you get

| Panel | What it shows |
|---|---|
| **Network State** | Auto-detected model architecture (real layer names + param counts), animated activation flow, accuracy ring on the output, overfitting halo |
| **Learning Curve** | Per-epoch primary-metric trajectory with grade-threshold reference lines and a smoothing slider |
| **Phase Journey** | Awakening → Learning → Understanding → Mastering → Polishing ribbon with per-phase grades |
| **Skill Dimensions** | Task-aware radar — mAP50 / Precision / Recall / Localisation for detection runs, Accuracy / Fitting / Generalisation for classification, 1−EER / TAR for biometrics, and so on |
| **Live Metrics** | TensorBoard-style scalar cards — latest value, ▲/▼ delta vs previous epoch, gradient-area sparkline of the full trend |
| **Distributions** | Parameter share by layer, min/IQR/median/max metric box-summary, value histograms |
| **Engineer Panel** | Loss / Accuracy / Overfitting-gap / LR-schedule (log-y) charts with EMA smoothing, log-scale, x:epoch/step toggles, best-epoch markers, and a stats table |
| **Training Diagnostics** | Health score gauge + interpreted cards for overfitting, convergence (least-squares slope), stability (σ of Δ), generalisation |
| **In Plain English** | Non-technical narrative for the manager / collaborator who just wants to know "is it good?" |

---

## Two ways to run

### Sidecar mode (recommended — full features)

Install the Python sidecar once:

```bash
pip install model-story
```

Then in VS Code:

- Press **`Ctrl+Alt+M`** (or **`Cmd+Alt+M`** on macOS) to open the dashboard
- Right-click any `.log` file → **Model Story: Open Log File…**
- Or run **Model Story: Watch Active Terminal** to stream a live training session

The extension spawns the local server, points the webview at it, and streams
metrics + architecture into the dashboard live.

### Standalone mode (no Python required)

If `pip install model-story` isn't available, the extension still parses logs
in-process using a built-in TypeScript engine. Open a log file exactly the
same way; you'll get the core story (grade, phase, narrative, learning curve).
Some panels (per-metric series, detected architecture) stay sparse — that
data only exists in sidecar mode.

---

## Commands

| Command | Default keybinding |
|---|---|
| `Model Story: Open Dashboard` | `Ctrl+Alt+M` / `Cmd+Alt+M` |
| `Model Story: Open Log File…` | (right-click any `.log`) |
| `Model Story: Watch Active Terminal` | — |
| `Model Story: Export Current Run` | — |
| `Model Story: Compare Two Runs` | — |

---

## Settings

| Setting | Default | What it does |
|---|---|---|
| `modelStory.autoWatchTerminal` | `true` | Auto-open the dashboard when ML training is detected in an integrated terminal |
| `modelStory.taskHint` | `auto` | Force a task type: `classification` / `detection` / `regression` / `biometric` / `gaze` / `nlp` |
| `modelStory.useSidecar` | `auto` | Whether to use the Python sidecar when present (`auto` / `always` / `never`) |
| `modelStory.sidecarPath` | _(empty)_ | Override the path to the `model-story` executable |
| `modelStory.theme` | `auto` | Dashboard theme — `auto` follows VS Code's colour theme |
| `modelStory.locale` | `en` | UI language — `en` / `fa` (RTL) / `fr` |

---

## Supported log formats

PyTorch Lightning · Keras / TensorFlow · HuggingFace Trainer · Ultralytics YOLO ·
FastAI · Accelerate · plus a universal `key=value` / `key: value` / JSON
fragment fallback for arbitrary logs.

Task auto-detection looks at which canonical metrics show up (mAP for
detection, perplexity for NLP, EER for biometric, MAE for gaze, accuracy
for classification, etc.) and grades against task-appropriate thresholds.

---

## Repository · Issues · Docs

- GitHub: <https://github.com/model-story/model-story>
- Issues: <https://github.com/model-story/model-story/issues>
- Docs: <https://docs.model-story.dev>

Apache-2.0 licensed.
