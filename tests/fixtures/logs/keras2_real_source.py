"""A real Keras 2 (`tf.keras`) run, console output kept.

Keras 2 is what `pip install tensorflow` gave until 2.16: `Epoch 1/12` above a
`====` bar. A small MLP on scikit-learn's bundled digits (nothing is downloaded),
with a learning rate that drops on a plateau, so `lr` is in the log.

    Needs:  pip install "tensorflow==2.15.*" scikit-learn
    Run:    python keras2_real_source.py 1 > keras2_real_verbose1.log 2>&1
            python keras2_real_source.py 2 > keras2_real_verbose2.log 2>&1

Run from a neutral folder. Redirected, so Keras draws no live bar: this is what
a run sent to a file looks like, which is what epochix is usually given.
"""

from __future__ import annotations

import logging
import os
import sys
import warnings

# TensorFlow's start-up notices and Python warnings print the paths of the files
# that raised them; a fixture carries no machine paths. Importing it logs one
# such notice, so logging goes off before the import.
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

import tensorflow as tf  # noqa: E402
from sklearn.datasets import load_digits  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

tf.keras.utils.set_random_seed(7)

verbose = int(sys.argv[1]) if len(sys.argv) > 1 else 1
x, y = load_digits(return_X_y=True)
x_train, x_val, y_train, y_val = train_test_split(
    x / 16.0, y, test_size=0.25, random_state=7, stratify=y
)
model = tf.keras.Sequential(
    [
        tf.keras.layers.Input(shape=(64,)),
        tf.keras.layers.Dense(64, activation="relu"),
        tf.keras.layers.Dense(10, activation="softmax"),
    ]
)
model.compile(
    optimizer=tf.keras.optimizers.SGD(learning_rate=0.05),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)
model.fit(
    x_train,
    y_train,
    validation_data=(x_val, y_val),
    epochs=12,
    batch_size=32,
    verbose=verbose,
    callbacks=[tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", patience=1, factor=0.5)],
)
