# Quickstart

Get a live dashboard for your training run in under 60 seconds.

---

## 1. Install

```bash
pip install model-story
```

---

## 2. Pipe your training script

```bash
python train.py 2>&1 | model-story --live
```

Your browser opens automatically. The dashboard updates in real time.

---

## 3. Parse an existing log file

```bash
model-story train.log
```

---

## Common patterns

### PyTorch Lightning

```python
from model_story.integrations.lightning import StoryCallback
import lightning as pl

trainer = pl.Trainer(callbacks=[StoryCallback()])
trainer.fit(model, datamodule=dm)
```

### HuggingFace Trainer

```python
from model_story.integrations.hf import StoryCallback
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
%load_ext model_story

# Parse a finished log:
%model_story train.log

# Live mode — runs the next cell through model-story:
%%model_story --live
!python train.py
```

### Python SDK

```python
from model_story.sdk import LiveReporter

with LiveReporter(task="classification") as reporter:
    for epoch in range(50):
        # ... your training loop ...
        reporter.log(train_loss=loss.item(), val_accuracy=acc)
```

---

## CLI reference

```
model-story --help
```

| Command | Description |
|--|--|
| `model-story <file>` | Parse a finished log file |
| `model-story --live` | Pipe stdin in live mode |
| `model-story serve` | Start the dashboard server only |
| `model-story list` | List all saved runs |
| `model-story export <id> --format html` | Export a run |
| `model-story compare <id1> <id2>` | Side-by-side run comparison |
| `model-story prune --older-than 30d` | Delete old runs |

---

## Next steps

- [Supported frameworks](parsers.md) — see all supported log formats
- [Deployment](deployment.md) — share with your team
- [Plugins](plugins.md) — add support for custom frameworks
