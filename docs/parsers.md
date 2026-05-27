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

## Universal fallback

Matches any log that contains at least one of:

- `key=value` pairs
- `key: value` pairs (lower confidence)
- JSON fragments `{...}` containing numeric values

Confidence: `0.10` — it always fires as a last resort.

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
