"""A real scikit-learn `GridSearchCV` at `verbose=3`, console output kept.

One line a fit: its fold, its parameters and its score. With
`return_train_score` the score is printed as a `(train=…, test=…)` pair, and with
several `scoring` names each has its own column. scikit-learn's bundled digits,
nothing is downloaded.

    Needs:  pip install scikit-learn
    Run:    python gridsearch_real_source.py plain > gridsearch_real.log 2>&1
            python gridsearch_real_source.py train > gridsearch_real_train_score.log 2>&1
            python gridsearch_real_source.py multi > gridsearch_real_multimetric.log 2>&1

Run from a neutral folder.
"""

from __future__ import annotations

import sys

from sklearn.datasets import load_digits
from sklearn.model_selection import GridSearchCV
from sklearn.svm import SVC

mode = sys.argv[1]
x, y = load_digits(return_X_y=True)
search = GridSearchCV(
    SVC(),
    {"C": [0.1, 1, 10], "gamma": [0.001, 0.01]},
    cv=3,
    verbose=3,
    return_train_score=mode != "plain",
    scoring=["accuracy", "f1_macro"] if mode == "multi" else None,
    refit="accuracy" if mode == "multi" else True,
)
search.fit(x / 16.0, y)
print(f"Best parameters: {search.best_params_}")
print(f"Best score: {search.best_score_:.4f}")
