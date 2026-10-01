"""Train a small CNN with Keras and keep Keras's own console output.

scikit-learn's `digits` is 1,797 real 8x8 handwritten digit images bundled with
the library, so nothing is downloaded. Keras 3 runs here on the PyTorch backend.

    Needs:  pip install keras torch scikit-learn
    Run:    KERAS_BACKEND=torch python <this file> steady > keras_image_classifier.log 2>&1
            KERAS_BACKEND=torch python <this file> fast   > demo.log 2>&1

Two runs come from this script:

* `steady` — a small model at a modest learning rate, still improving at its
  last epoch. `epochix demo keras` plays it (demo/keras_image_classifier.log).
* `fast` — a larger model with a cosine learning-rate schedule that reaches its
  accuracy early. The VS Code extension's "Try a Demo Run" plays it
  (epochix-vscode/media/demo.log).

A third argument sets Keras's `verbose` level: 1 (the default) draws a progress
bar per epoch, 2 prints one line per epoch. Nothing is edited afterwards: the
log is the console output, byte for byte.
"""

from __future__ import annotations

import math
import os
import sys
import warnings

os.environ.setdefault("KERAS_BACKEND", "torch")

import keras  # noqa: E402
from sklearn.datasets import load_digits  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

VARIANT = sys.argv[1] if len(sys.argv) > 1 else "steady"
VERBOSE = int(sys.argv[2]) if len(sys.argv) > 2 else 1
EPOCHS = 20

# Python warnings print the path of the file that raised them; this log ships
# with the package, so it carries no machine paths.
warnings.filterwarnings("ignore")


def steady() -> tuple[keras.Model, float, int, list[keras.callbacks.Callback]]:
    model = keras.Sequential(
        [
            keras.Input(shape=(8, 8, 1)),
            keras.layers.Conv2D(16, 3, padding="same", activation="relu"),
            keras.layers.MaxPooling2D(),
            keras.layers.Flatten(),
            keras.layers.Dense(32, activation="relu"),
            keras.layers.Dense(10, activation="softmax"),
        ]
    )
    return model, 5e-4, 32, []


def fast() -> tuple[keras.Model, float, int, list[keras.callbacks.Callback]]:
    model = keras.Sequential(
        [
            keras.Input(shape=(8, 8, 1)),
            keras.layers.Conv2D(32, 3, padding="same", activation="relu"),
            keras.layers.MaxPooling2D(),
            keras.layers.Conv2D(64, 3, padding="same", activation="relu"),
            keras.layers.MaxPooling2D(),
            keras.layers.Flatten(),
            keras.layers.Dense(128, activation="relu"),
            keras.layers.Dropout(0.3),
            keras.layers.Dense(10, activation="softmax"),
        ]
    )
    peak = 2e-3

    def cosine(epoch: int, _lr: float) -> float:
        return 0.5 * peak * (1 + math.cos(math.pi * epoch / EPOCHS))

    return model, peak, 64, [keras.callbacks.LearningRateScheduler(cosine)]


def main() -> None:
    seed = 11 if VARIANT == "steady" else 7
    keras.utils.set_random_seed(seed)
    digits = load_digits()
    x = (digits.images / 16.0).astype("float32")[..., None]
    x_train, x_val, y_train, y_val = train_test_split(
        x, digits.target, test_size=0.25, random_state=seed, stratify=digits.target
    )

    model, lr, batch, callbacks = {"steady": steady, "fast": fast}[VARIANT]()
    model.compile(
        optimizer=keras.optimizers.Adam(lr),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    model.summary()
    model.fit(
        x_train,
        y_train,
        validation_data=(x_val, y_val),
        epochs=EPOCHS,
        batch_size=batch,
        callbacks=callbacks,
        verbose=VERBOSE,
    )


if __name__ == "__main__":
    main()
