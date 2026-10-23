# Test logs

Every log here is one of two things, and this file says which.
`tests/unit/test_fixture_provenance.py` fails when a log is in neither list,
or when a listed script is missing.

## Recorded runs

The console output of a real run, byte for byte, progress-bar redraws
included. Record one again from a neutral folder (the libraries print the
paths they use); never edit a capture by hand.

| Log | The run | Script |
|---|---|---|
| `accelerate_real.log` | `accelerator.print({...})` of a dict with the global `step`, from a small loop run through Accelerate 1.15, 4 epochs. | `accelerate_real_source.py` |
| `catboost_real_classifier.log` | CatBoost classifier, `eval_metric="AUC"`, breast cancer data. | `boosting_real_source.py` (`cb_clf`) |
| `catboost_real_no_eval_set.log` | CatBoost classifier fitted with no eval set. | `boosting_real_source.py` (`cb_no_eval_set`) |
| `catboost_real_regressor.log` | CatBoost regressor stopped by its overfitting detector. | `boosting_real_source.py` (`cb_reg`) |
| `catboost_real_two_eval_sets.log` | CatBoost regressor with two eval sets. | `boosting_real_source.py` (`cb_two_eval_sets`) |
| `fastai_real.log` | fastai 2.8's results table from a tabular learner, 4 epochs. | `fastai_real_source.py` |
| `huggingface_real_trainer.log` | A small MLP trained with `transformers.Trainer` (transformers 5). | `huggingface_real_source.py` |
| `keras_real_verbose2.log` | The demo CNN with Keras 3, `verbose=2`. | `../../../demo/keras_image_classifier_source.py` (`steady 2`) |
| `lightgbm_real_classifier.log` | LightGBM classifier, two eval sets. | `boosting_real_source.py` (`lgb_clf`) |
| `lightgbm_real_early_stopping.log` | LightGBM's native API with early stopping. | `boosting_real_source.py` (`lgb_native`) |
| `resnet18_cifar10.log` | ResNet-18 on CIFAR-10, a hand-written PyTorch loop that prints its own lines. | `resnet18_cifar10_source.py` |
| `tqdm_loop_real.log` | A hand-written PyTorch loop with a tqdm bar over the training and the validation batches, `set_postfix` carrying the numbers. | `tqdm_loop_real_source.py` |
| `xgboost_real_classifier.log` | XGBoost classifier, two eval sets, two metrics. | `boosting_real_source.py` (`xgb_clf`) |
| `yolo_real_ultralytics.log` | Ultralytics 8.4 on coco8, 3 epochs on CPU. | `../../../demo/yolov8_detection_source.py` (`3 coco8 320 cpu`) |

## Format samples

Written by hand to put a parser in front of a particular layout or edge case.
Their numbers are not measurements of anything, and a story told from one says
nothing about a real run.

| Log | The layout | Is it one a library prints? |
|---|---|---|
| `ansi_colors.log` | Keras 2 lines wrapped in ANSI colour codes. | An edge case. |
| `detection_coco.log` | Ultralytics 8.0's table, with the `Size` column, validating every few epochs. | The table, yes; its schedule was chosen. |
| `diverging_loss.log` | The tqdm-loop layout below, with the loss climbing. | An edge case. |
| `empty.log` | Nothing. | An edge case. |
| `garbage.log` | A web server's log. | Not training output. |
| `gridsearch_cv.log` | scikit-learn's `GridSearchCV` at `verbose=3`. | Yes; the scores were typed. |
| `hf_classification.log` | Older `transformers.Trainer` dicts, numbers as floats. | Yes (transformers 4); `transformers 5` prints strings — see `huggingface_real_trainer.log`. |
| `huggingface_5ep.log` | The same, 5 epochs. | As above. |
| `huggingface_nlp_10ep.log` | The same, with an `eval_perplexity` a `compute_metrics` would add. | As above. |
| `interrupted.log` | The tqdm-loop layout, cut off mid-epoch. | An edge case. |
| `keras_100ep.log` | Keras 2 (`tf.keras`) at `verbose=1`: `1563/1563 [====] - 8s 5ms/step - loss: …`. | Yes, Keras 2; Keras 3 prints `━━━` bars — see `keras_real_verbose2.log`. |
| `keras_50ep.log` | The same, 50 epochs. | As above. |
| `keras_short.log` | The same, 10 epochs. | As above. |
| `mixed_frameworks.log` | Keras 2 lines, then older `Trainer` dicts, in one log. | An edge case. |
| `multiline_json.log` | Older `Trainer` dicts, logged every half epoch. | As `hf_classification.log`. |
| `no_val_metrics.log` | The tqdm-loop layout with no validation. | An edge case. |
| `pl_high_accuracy.log` | The tqdm-loop layout below. | As below. |
| `plateau.log` | The tqdm-loop layout without timings, accuracy flattening. | An edge case. |
| `pytorch_lightning_30ep.log` | `Epoch 1/30: 100%\|…\| 250/250 [00:03<00:00, loss=…, acc=…]`, a training and a validation bar per epoch. | **Not PyTorch Lightning**, whatever the name says: Lightning counts epochs from 0 and puts every metric on one bar (see `../../../demo/seq2seq_attention.log`). It is a hand-written loop's tqdm bars, minus tqdm's rate — `tqdm_loop_real.log` is the real thing. |
| `pytorch_lightning_long.log` | The same, 100 epochs. | As above. |
| `pytorch_lightning_short.log` | The same, 5 epochs. | As above. |
| `scientific_notation.log` | The tqdm-loop layout with numbers in `1e-03` form. | An edge case. |
| `single_epoch.log` | Keras 2, one epoch. | An edge case. |
| `universal_20ep.log` | `[Epoch 1/20] train_loss=… val_accuracy=…` from a loop's own `print`. | Any loop can print it. |
| `universal_kv_colon.log` | The same, 30 epochs. | As above. |
| `yolo_100ep.log` | An Ultralytics-like table. | **No.** No `Size` column, a made-up "YOLOv8 training started" header, validation every fifth epoch where Ultralytics validates every epoch. Real runs: `yolo_real_ultralytics.log` and `../../../demo/yolov8_detection.log`. |
| `yolo_50ep.log` | The same, 50 epochs. | As above. |
| `yolo_short.log` | The same, 10 epochs. | As above. |
