# Quickstart

Get a live dashboard for your training run in under 60 seconds.

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

---

## CLI reference

```
epochix --help
```

| Command | Description |
|--|--|
| `epochix <file>` | Parse a finished log file |
| `epochix --live` | Pipe stdin in live mode |
| `epochix serve` | Start the dashboard server only |
| `epochix list` | List all saved runs |
| `epochix export <id> --format html` | Export a run |
| `epochix compare <id1> <id2>` | Side-by-side run comparison |
| `epochix prune --older-than 30d` | Delete old runs |

---

## Next steps

- [Supported frameworks](parsers.md) — see all supported log formats
- [Deployment](deployment.md) — share with your team
- [Plugins](plugins.md) — add support for custom frameworks
