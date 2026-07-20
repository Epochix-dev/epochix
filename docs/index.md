# Epochix

**See what your model is actually doing — training logs become a plain-English story with a letter grade.**

![Epochix turns a training log into an animated dashboard with a plain-English story and a letter grade](https://raw.githubusercontent.com/epochix-dev/epochix/main/asset/epochix_demo.gif)

Turn raw terminal output from any ML framework into an animated, plain-English narrative — with a letter grade, a live brain visualization, and an exportable HTML report. No code changes required.

**Easiest — in VS Code, no setup:** install the
[Epochix extension](https://marketplace.visualstudio.com/items?itemName=epochix.epochix),
click the **E** icon in the sidebar, and hit **▶ Try a Demo Run**. Training you
run in the integrated terminal is detected automatically.

**Or from a terminal:**

```bash
pip install epochix
python train.py 2>&1 | epochix --live
```

---

## Why epochix?

Existing tools (TensorBoard, W&B, MLflow) are designed for ML engineers. epochix is designed for *everyone*:

| | epochix | W&B / TensorBoard |
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
- [Deployment](deployment.md) — local server, team server, reverse proxy

---

## Installation

=== "pip"
    ```bash
    pip install epochix
    ```

=== "with Lightning"
    ```bash
    pip install "epochix[lightning]"
    ```

=== "with HuggingFace"
    ```bash
    pip install "epochix[hf]"
    ```

=== "everything"
    ```bash
    pip install "epochix[all]"
    ```
