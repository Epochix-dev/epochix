# Demo logs

## Recorded runs

These are the console output of real training runs, kept byte for byte —
progress-bar redraws included. Each has the script that produced it beside it,
and these three are the ones `epochix demo` plays (the package ships copies in
`src/epochix/_demos/`).

| Log | The run | Script |
|---|---|---|
| `keras_image_classifier.log` | A small CNN on scikit-learn's handwritten digits (1,797 images, bundled with the library). 20 epochs. | `keras_image_classifier_source.py` |
| `seq2seq_attention.log` | A GRU encoder-decoder with additive attention, French to English, on the sentence pairs from the PyTorch seq2seq tutorial. PyTorch Lightning, 20 epochs. `val_acc` is token accuracy with teacher forcing. Validation loss bottoms out around epoch 13 and rises: a real, mild overfit. | `seq2seq_attention_source.py` |
| `yolov8_detection.log` | YOLOv8n fine-tuned with Ultralytics on COCO128, 30 epochs. COCO128 validates on the images it trains on, so the mAP shows the detector fitting them, not generalising. | `yolov8_detection_source.py` |

To record one again, put the data the script's docstring names beside it and
run it from a neutral folder: the libraries print the paths they use, and the
log is published.

## Format samples

`fingerprint_matching.log`, `gaze_estimation.log`, `huggingface_bert.log` and
`pytorch_lightning.log` are **not recordings**. They were written by hand to
exercise the parsers on a particular layout, and the tests use them as
fixtures. Their numbers are not measurements of anything.
