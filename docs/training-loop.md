# Writing your own training loop

You do not need to integrate with epochix. If your loop prints its metrics —
and most loops already do — that is the integration.

## The whole thing

```python
for epoch in range(1, EPOCHS + 1):
    ...
    print(f"Epoch {epoch}/{EPOCHS} train_loss={loss:.4f} val_accuracy={acc:.4f}", flush=True)
```

```bash
python train.py | epochix
```

That is a complete setup. Piped input is detected automatically, the task type
is inferred from your metric names, and the dashboard opens as the run
progresses. Add `--headless` to skip the browser (useful in CI).

!!! tip "Use `flush=True`"

    Python buffers stdout when it is piped rather than attached to a terminal.
    Without `flush=True` your metrics arrive in one burst at the end, so the
    dashboard cannot draw the run *while* it trains. Alternatively run
    `python -u train.py`.

## Shapes that are recognised

Any of these work, and they can be mixed:

```text
Epoch 3/10 train_loss=0.4413 val_accuracy=0.8590
epoch: 3  loss: 0.4413  val_acc: 0.8590
{"epoch": 3, "train_loss": 0.4413, "val_acc": 0.8590}
```

A bare `Epoch N/M` header is understood too, so metrics printed on the
following line are still attributed to the right epoch — and the `/M` gives the
progress bar something to fill.

The epoch may appear anywhere on the line, including after the metrics.

## Name your metrics conventionally

Metric names are what tell epochix which task you are training and how to grade
it, so the names matter more than the format.

| Use | For |
|---|---|
| `train_loss`, `val_loss`, `loss` | any run |
| `val_accuracy` / `val_acc`, `f1`, `auc` | classification |
| `mae`, `rmse`, `mse`, `r2` | regression |
| `map50`, `map`, `precision`, `recall` | detection |
| `perplexity` | language modelling |
| `lr` | learning-rate schedule |

An unrecognised name still charts, but the run falls back to the `custom` task,
which is graded on its improvement trajectory rather than an absolute scale.

A run that logs only a loss curve is fine — it is graded on how much the loss
improved from its own starting point, not against an accuracy scale.

## What not to print

Some things look like metrics and are not, so epochix deliberately ignores
them. Printing them will not enrich the dashboard:

- **Run configuration** — `batch_size`, `num_workers`, `epochs`, `precision`.
  These are constants, and charting one draws a flat line beside your real
  curves as though the model were doing something.
- **`print(model)` layer arguments** — `kernel_size`, `in_features`, `stride`.
  The architecture panel reads a model dump when one is present, but those
  values are shapes, not measurements.
- **tqdm and download bars.** A progress bar is not a metric.

`lr` is the exception: a learning-rate schedule is a real curve and is charted.

## Writing to a file instead

If you would rather keep a log file, epochix reads it afterwards:

```bash
python train.py | tee train.log
epochix run train.log
```

To watch a file that another process is still writing, use `--tail`. To follow
one on another machine, use `--ssh`. Both are documented under
`epochix run --help`.

## When the dashboard is not what you expected

```bash
epochix check train.log
```

This reports exactly which lines were parsed, which metrics were found, what
task was inferred, and what to add. It stores nothing and serves nothing — it
only explains. Reach for it before assuming something is broken; an empty
dashboard is nearly always a log whose metrics were not in a recognised shape.

## If you would rather call an API

There is a Python SDK for logging directly from inside your code, including
live reporting while a run is in progress — see the
[Python SDK reference](api.md). It is strictly optional; printing is the
supported path and nothing about it is second class.
