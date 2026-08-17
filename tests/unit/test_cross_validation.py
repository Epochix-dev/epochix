"""Cross-validation folds are a distribution, not a trajectory.

Five folds were charted in the order they finished, as though the model were
improving across them. Shuffle the data and the line points the other way — the
slope is pure noise, drawn as signal. The printed mean was then picked up as a
sixth fold, mixing a summary into the series it summarises.

Every sample here is real output, captured by running scikit-learn:
``cross_val_score(verbose=3)``, ``GridSearchCV(verbose=3)``, and the loop most
people write by hand. The three formats disagree in ways that are easy to get
wrong from memory — one names the metric, two call it "score", and GridSearchCV
prints the candidate's hyperparameters on the same row.
"""

from __future__ import annotations

from statistics import fmean

from epochix.parsers.base import ParserContext
from epochix.parsers.universal import UniversalParser

# cross_val_score(clf, X, y, cv=5, verbose=3)
CV_VERBOSE = [
    "[CV] END ................................ score: (test=0.938) total time=   0.0s",
    "[CV] END ................................ score: (test=0.894) total time=   0.0s",
    "[CV] END ................................ score: (test=0.919) total time=   0.0s",
    "[CV] END ................................ score: (test=0.906) total time=   0.0s",
    "[CV] END ................................ score: (test=0.869) total time=   0.0s",
]

# GridSearchCV(clf, {"max_depth": [3, 8]}, cv=3, verbose=3).fit(X, y)
CV_GRIDSEARCH = [
    "Fitting 3 folds for each of 2 candidates, totalling 6 fits",
    "[CV 1/3] END .......................max_depth=3;, score=0.933 total time=   0.0s",
    "[CV 2/3] END .......................max_depth=3;, score=0.884 total time=   0.0s",
    "[CV 3/3] END .......................max_depth=8;, score=0.940 total time=   0.0s",
]

# The loop most people write.
CV_HANDWRITTEN = [
    "Running 5-fold cross-validation...",
    "Fold 1: accuracy = 0.9375",
    "Fold 2: accuracy = 0.8938",
    "Fold 3: accuracy = 0.9187",
    "Fold 4: accuracy = 0.9062",
    "Fold 5: accuracy = 0.8688",
    "Mean accuracy: 0.9050 (+/- 0.0232)",
]


def _parse(lines: list[str]) -> tuple[list[tuple[str, float]], list[tuple[str, float]], dict]:
    """Return (emitted during the pass, emitted at flush, collected folds)."""
    parser = UniversalParser()
    ctx = ParserContext(run_id="cv")
    during: list[tuple[str, float]] = []
    for i, line in enumerate(lines):
        ctx.seq = i
        for metric in parser.parse_line(line, ctx):
            during.append((metric.key, metric.value))
    flushed = [(m.key, m.value) for m in parser.flush(ctx)]
    return during, flushed, dict(ctx.extra.get("cv_folds") or {})


class TestFoldsAreNotAxisPoints:
    def test_folds_do_not_become_a_series(self) -> None:
        during, _, folds = _parse(CV_HANDWRITTEN)
        # The five fold readings are collected, not charted.
        assert folds["accuracy"] == [0.9375, 0.8938, 0.9187, 0.9062, 0.8688]
        # Only the printed mean reaches the chart — one point, no slope.
        assert during == [("accuracy", 0.9050)]

    def test_the_printed_mean_is_not_a_sixth_fold(self) -> None:
        during, flushed, _ = _parse(CV_HANDWRITTEN)
        values = [v for k, v in during + flushed if k == "accuracy"]
        assert values == [0.9050], values

    def test_a_run_without_a_printed_mean_gets_one(self) -> None:
        """scikit-learn's own verbose output never prints the mean."""
        during, flushed, folds = _parse(CV_VERBOSE)
        assert during == []
        assert len(folds["score"]) == 5
        assert flushed == [("score", fmean([0.938, 0.894, 0.919, 0.906, 0.869]))]

    def test_the_spread_is_kept_for_reporting(self) -> None:
        """The spread is the whole reason to cross-validate, and the one thing
        a mean cannot tell you."""
        _, _, folds = _parse(CV_VERBOSE)
        assert min(folds["score"]) == 0.869
        assert max(folds["score"]) == 0.938


class TestGridSearchRowsAreConfigurationPlusScore:
    def test_hyperparameters_on_a_fold_row_are_not_metrics(self) -> None:
        """GridSearchCV prints the candidate being tried next to its score.

        `max_depth=3` is a setting; charting it puts a hyperparameter on the
        same footing as a result — the estimator-repr fault in a new place.
        """
        during, flushed, folds = _parse(CV_GRIDSEARCH)
        assert during == []
        assert set(folds) == {"score"}, folds
        assert [k for k, _ in flushed] == ["score"]

    def test_the_timing_column_is_not_a_metric_either(self) -> None:
        _, _, folds = _parse(CV_GRIDSEARCH)
        assert "time" not in folds
        assert "total" not in folds


class TestOrdinaryLogsAreUnaffected:
    def test_a_normal_epoch_line_still_parses(self) -> None:
        during, flushed, folds = _parse(
            [
                "Epoch 1/10 train_loss=0.5 val_accuracy=0.8",
                "Epoch 2/10 train_loss=0.3 val_accuracy=0.9",
            ]
        )
        assert folds == {}
        assert flushed == []
        assert during == [
            ("train_loss", 0.5),
            ("val_accuracy", 0.8),
            ("train_loss", 0.3),
            ("val_accuracy", 0.9),
        ]

    def test_a_line_merely_mentioning_folds_is_not_a_fold_row(self) -> None:
        during, _, folds = _parse(["Running 5-fold cross-validation...", "Loaded fold data"])
        assert folds == {}
        assert during == []
