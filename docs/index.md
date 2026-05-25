# Model Learning Story

**Visual storytelling for deep learning training runs.**

Turn raw terminal output from any ML framework into an animated, plain-English narrative — with a letter grade, a live brain visualization, and an exportable HTML report. No code changes required.

```bash
pip install model-story
python train.py 2>&1 | model-story --live
```

---

## Why model-story?

Existing tools (TensorBoard, W&B, MLflow) are designed for ML engineers. model-story is designed for *everyone*:

| | model-story | W&B / TensorBoard |
|--|--|--|
| Non-technical narrative + letter grade | ✓ | ✗ |
| Animated living visuals (not just charts) | ✓ | ✗ |
| Zero code changes — parses stdout | ✓ | ✗ |
| Standalone shareable HTML | ✓ | partial |
| Local-first, no account required | ✓ | ✗ |

---

## Quick links

- [Quickstart](quickstart.md) — up and running in under 60 seconds
- [Supported frameworks](parsers.md) — PyTorch Lightning, Keras, HuggingFace, YOLO, FastAI, Accelerate, and more
- [Python SDK](api.md) — `LiveReporter`, `parse()`, `compare()`
- [Plugins](plugins.md) — write a custom parser or metaphor pack
- [Deployment](deployment.md) — local server, team server, Docker

---

## Installation

=== "pip"
    ```bash
    pip install model-story
    ```

=== "with Lightning"
    ```bash
    pip install "model-story[lightning]"
    ```

=== "with HuggingFace"
    ```bash
    pip install "model-story[hf]"
    ```

=== "full"
    ```bash
    pip install "model-story[full]"
    ```
