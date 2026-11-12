# Supported Frameworks

epochix auto-detects the framework from your log output.
The detection uses a "sniff" score — the parser with the highest confidence
above the threshold wins. The universal fallback always fires if nothing
else matches.

---

## PyTorch Lightning

**Auto-detection regex:**

```
Epoch \d+/\d+:.*\|
```

**Sample log line:**

```
Epoch 5/50: 100%|=====>| 250/250 [00:12<00:00, loss=0.432, val_acc=0.867]
```

**Detected metrics:** Any `key=value` pair inside the progress bar line.

---

## Keras / TensorFlow

**Auto-detection:** `Epoch N/N` header + progress bar `[====>]`

**Sample:**

```
Epoch 5/50
1563/1563 [==============================>] - 10s - loss: 0.423 - accuracy: 0.867 - val_loss: 0.401 - val_accuracy: 0.874
```

**Detected metrics:** All `key: value` pairs on the progress bar line.

---

## HuggingFace Transformers

**Auto-detection:** JSON-like dict with `'loss'` key.

**Sample:**

```
{'loss': 0.5123, 'learning_rate': 5e-05, 'epoch': 1.0}
{'eval_loss': 0.3421, 'eval_accuracy': 0.8765, 'epoch': 1.0}
```

**Detected metrics:** All numeric values in the dict.

---

## Ultralytics YOLO

**Auto-detection:** Training row `epoch/total GPU_mem box_loss cls_loss dfl_loss`
and validation row `all N N precision recall mAP50 mAP50-95`.

**Sample:**

```
      5/50     1.23G   0.456   0.234   0.123   128
                 all   5000   5000   0.712   0.654   0.678   0.432
```

**Detected metrics:** `box_loss`, `cls_loss`, `dfl_loss`, `precision`, `recall`, `mAP50`, `mAP`.

---

## FastAI

**Auto-detection:** Tabular header `train_loss  valid_loss  metric  time`.

**Sample:**

```
epoch  train_loss  valid_loss  accuracy   time
0      1.4321      1.2345      0.4567     00:12
1      0.9876      0.8765      0.5678     00:11
```

---

## Accelerate

**Auto-detection:** JSON-like dict (same format as HuggingFace).

---

## PyTorch example meters

The `AverageMeter` / `ProgressMeter` rows of the PyTorch ImageNet example
(`pytorch/examples`, `imagenet/main.py`), which a great deal of research code
copied with it.

**Auto-detection:** two or more rows opening `Epoch: [N][i/n]` or `Test: [i/n]`.

**Sample** (the columns are tab separated):

```
Epoch: [0][16/32]  Time  0.544 ( 0.530)  Data  0.036 ( 0.047)  Loss 2.2088e+00 (3.6574e+00)  Acc@1  18.75 (  8.79)  Acc@5  62.50 ( 45.12)
Test: [ 6/10]  Time  0.175 ( 0.180)  Loss 5.8603e+00 (4.7599e+00)  Acc@1   0.00 ( 15.62)  Acc@5  37.50 ( 51.04)
 *   Acc@1 10.333 Acc@5 64.667
```

**What is read:**

- From a training row, the loss of that batch, placed at the fraction of the
  epoch the row states (batch 16 of 32 in epoch 0 is 0.5 epochs in).
- From the ` *` line, the validation result — `Acc@1` as validation accuracy,
  `Acc@5` as top-5 accuracy — at the number of epochs finished, together with
  the training accuracy of that epoch: the running average in brackets on its
  last training row.
- `Acc@k` is a percentage and is stored as a fraction.

**What is not:** a `Test:` row (a validation pass caught part-way through),
the training rows' `Acc@5`, and the `Time` and `Data` timers.

Until the first validation result the run has printed only a loss, so that is
what the story is told by; from then on it is told by validation accuracy.

---

## A run-long step bar

One tqdm bar for the whole training, described `Steps`, as the diffusers
training scripts draw (`train_dreambooth_lora_sdxl.py` and its siblings). The
bar is everything such a run prints about how it is going.

**Auto-detection:** two or more redraws of a bar described `Steps` (or
`steps`) that carries `key=value` pairs.

**Sample:**

```
Steps:  32%|###2      | 39/120 [00:26<00:43,  1.85it/s, loss=0.0129, lr=0.0001]
```

**What is read:** every `key=value` on the bar, each time the values change,
at the step the bar stands at; the bar's total is the run's length. The step
is the x-axis: there is no epoch to count.

The bar is redrawn in place — in a file, a 1,500-step run is a handful of
lines — so this bar's redraws are read one by one where every other line is
read in its final state. A live run is read as the redraws arrive, in the VS
Code terminal and from a tailed file. Piped to `epochix -` on Linux or macOS,
or tailed over SSH, it is read when each line ends, which for this bar is at a
checkpoint or at the end of the run.

What the bar carries is the loss of ONE batch. For a diffusion model that
number depends mostly on which noise level the batch drew, so it jumps from
step to step by an order of magnitude on a healthy run. Such a run is charted
as logged and [not given a letter](training-loop.md#readings-that-cannot-be-compared):
one reading does not say where it is.

---

## Universal fallback

Matches any log that contains at least one of:

- `key=value` pairs
- `key: value` pairs (lower confidence)
- JSON fragments `{...}` containing numeric values

Confidence: `0.10` — it always fires as a last resort.

### Loops that count steps

A row that opens with a counter (`epoch`, `step`, `iter`, `iteration`, `batch`
or `round`, then a number) may carry its metrics as bare `name value` pairs,
as nanoGPT's training loop and the many loops written after it do:

```
step 250: train loss 2.4293, val loss 2.4447
iter 260: loss 2.4461, time 16.42ms, mfu 0.08%
```

- The name must be a metric Epochix recognises; `mfu` above is not read.
- A split word in front of the name belongs to it: `val loss` is the
  validation loss, not a second training loss.
- The value ends at a space, a comma, a semicolon or the end of the line. A
  number glued to its unit (`16.42ms`, `0.08%`) is not a value.
- A line that does not open with a counter is prose, and is not read this way.

A run that prints `step N` and never an epoch is told by step: the step is its
x-axis, as an iteration or a boosting round is. Once an epoch is printed, a
step counts within it.

Python source echoed to the console is settings, not results: an assignment
followed by a `#` comment (`learning_rate = 1e-3 # ...`), and the lines
nanoGPT's configurator opens with `Overriding`.

---

## Not read yet

- **MLX-LM** (`Iter 10: Train loss ..., Learning Rate ..., It/sec ...`) has
  not been recorded: it needs Apple silicon. Its layout is not in the tests,
  and nothing here was written for it.
- **kohya-ss `sd-scripts`** draws a bar described `steps` with `avr_loss=...`.
  The step-bar parser accepts the description in either case, but no kohya run
  has been recorded, and `avr_loss` is not a name Epochix recognises.

---

## LLM fallback (opt-in)

For completely unrecognised formats, an optional LLM-powered extractor
can be enabled:

```bash
# Ollama (local)
export EPOCHIX_LLM_URL=http://localhost:11434
epochix train.log

# OpenAI
export EPOCHIX_LLM_KEY=sk-...
epochix train.log
```

The LLM fallback batches 20 lines per call and asks the model to extract
`{key, value, epoch}` tuples as JSON. It has a confidence of `0.55` —
lower than all regex parsers.

---

## Writing a custom parser

See [Plugins](plugins.md).
