# Already using W&B, TensorBoard, or plain logs?

Epochix isn't a replacement for your experiment tracker. It answers a different
question.

A tracker records **what happened across many runs** — every metric, every
config, every sweep, kept so you can compare them later. Epochix reads **one
run** and tells you, in words, what it means: where the model peaked, whether it
is overfitting, what the best epoch actually was, and a letter grade with its
reasoning attached.

You can keep your tracker and point Epochix at runs you already have.

## From a plain log file — nothing installed, nothing changed

This is the main path and needs no integration at all. If your training script
prints anything resembling metrics, Epochix reads it:

```bash
python train.py | epochix
```

Already finished? Point it at the file:

```bash
epochix run train.log
```

This works on logs you did not write — a colleague's, a cluster job's, one from
six months ago. There is no SDK call to add and nothing to instrument, which is
the part a tracker cannot do retroactively.

Not sure whether your log is readable? Ask before committing to anything:

```bash
epochix check train.log
```

It reports what it can and cannot extract, and what to add to your prints if
something is missing.

## From TensorBoard

Reads the event files straight off disk. No account, no network, no login:

```bash
epochix import-tensorboard runs/experiment_1
```

Point it at the directory containing `events.out.tfevents.*`. Every
sub-directory becomes its own run, so a logdir holding several experiments
imports all of them.

## From Weights & Biases

### From a run already on your disk — no account needed

Every W&B run writes a directory. Point Epochix at it:

```bash
epochix import-wandb wandb/
```

That reads the run history straight off local disk — no login, no API key, no
network. It accepts your `wandb/` directory, a single run directory inside it,
or the `run-*.wandb` file itself, and imports every run it finds.

This works for runs logged with `WANDB_MODE=offline` as well as ordinary ones,
because the local directory is written either way.

Requires `pip install wandb` — the file is a binary record log, and Epochix
uses W&B's own reader for it rather than guessing at the format.

### From the W&B servers

If the run is not on this machine, fetch it by reference:

```bash
epochix import-wandb myteam/bert-finetune/a1b2c3d4
```

!!! note "This form needs credentials"

    Anything that is not an existing path is treated as
    `entity/project/run_id` and fetched through the W&B API, which needs an
    API key — set `WANDB_API_KEY` or pass `--api-key`.

## What you get that a tracker doesn't

A tracker draws the curve. Epochix reads it:

> **lower-lr finished ahead of baseline: 0.8970 against 0.8460 (val_accuracy).**
> baseline peaked at 0.8650 on epoch 7 and ended worse, at 0.8460. Had it
> stopped at its best the gap would have been 0.0320 rather than 0.0510.
> lower-lr was still improving when it stopped, so its result is probably not
> its ceiling.

Plus a letter grade, an animated GIF you can drop into a slide or a PR, and a
single-file HTML report that opens offline.

## What it deliberately will not do

Epochix does not manage sweeps, host a model registry, track artifact lineage,
or coordinate a team. Those are what a tracker is for, and W&B, MLflow and
Neptune do them well.

It also refuses to state things it cannot support. A grade is compared against
absolute per-task thresholds, so it cannot know that 85% on your dataset is
excellent where 85% on MNIST is poor — and the dashboard says so on the card
rather than leaving you to assume otherwise. Metric values that are impossible
for the quantity in question are reported as impossible instead of narrated as
fact.
