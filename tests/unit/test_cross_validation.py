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


# GridSearchCV with two parameters varying, and with multi-metric scoring.
GRID_TWO_PARAMS = [
    "Fitting 3 folds for each of 4 candidates, totalling 12 fits",
    "[CV 1/3] END .......criterion=gini, max_depth=3;, score=0.920 total time=   0.0s",
    "[CV 2/3] END .......criterion=gini, max_depth=3;, score=0.950 total time=   0.0s",
    "[CV 1/3] END .......criterion=gini, max_depth=8;, score=0.940 total time=   0.0s",
    "[CV 2/3] END .......criterion=gini, max_depth=8;, score=0.980 total time=   0.0s",
]

GRID_MULTI_METRIC = [
    "Fitting 2 folds for each of 2 candidates, totalling 4 fits",
    "[CV 1/2] END max_depth=3; accuracy: (test=0.923) f1: (test=0.924) total time=   0.0s",
    "[CV 2/2] END max_depth=3; accuracy: (test=0.937) f1: (test=0.939) total time=   0.0s",
    "[CV 1/2] END max_depth=8; accuracy: (test=0.937) f1: (test=0.937) total time=   0.0s",
    "[CV 2/2] END max_depth=8; accuracy: (test=0.970) f1: (test=0.970) total time=   0.0s",
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


def _candidates(lines: list[str]) -> dict[str, dict[str, list[float]]]:
    parser = UniversalParser()
    ctx = ParserContext(run_id="cv")
    for i, line in enumerate(lines):
        ctx.seq = i
        parser.parse_line(line, ctx)
    return dict(ctx.extra.get("cv_candidates") or {})


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


class TestASearchReportsTheCandidateItChose:
    """Folds of different candidates are not one population.

    0.5.98 averaged all of them, which answers a question nobody asked: a
    search is run to find the best setting, and a mean over every setting tried
    hides exactly that.
    """

    def test_folds_are_grouped_by_parameter_set(self) -> None:
        cands = _candidates(GRID_TWO_PARAMS)
        assert set(cands) == {"criterion=gini, max_depth=3", "criterion=gini, max_depth=8"}
        assert cands["criterion=gini, max_depth=8"]["score"] == [0.940, 0.980]

    def test_the_winning_candidate_is_charted(self) -> None:
        _, flushed, _ = _parse(GRID_TWO_PARAMS)
        # Best is gini/max_depth=8 at (0.940 + 0.980) / 2 = 0.960.
        # The mean across ALL four fold results would be 0.9475 — a number that
        # describes no candidate the search actually tried.
        assert flushed == [("score", 0.960)]

    def test_every_metric_is_grouped_when_scoring_is_multi_metric(self) -> None:
        cands = _candidates(GRID_MULTI_METRIC)
        assert set(cands) == {"max_depth=3", "max_depth=8"}
        assert cands["max_depth=8"]["accuracy"] == [0.937, 0.970]
        assert cands["max_depth=8"]["f1"] == [0.937, 0.970]

    def test_multi_metric_rows_do_not_leak_parameters(self) -> None:
        """These rows name each score ("accuracy: (test=0.923)") rather than
        calling it "score", so they missed the score pattern and fell through
        to the ordinary key=value scan — which took `max_depth` from the
        parameter set and `test` twice."""
        _, _, folds = _parse(GRID_MULTI_METRIC)
        assert set(folds) == {"accuracy", "f1"}, folds

    def test_a_plain_cross_validation_has_no_candidates(self) -> None:
        """cross_val_score tries one setting and prints no parameters."""
        assert _candidates(CV_VERBOSE) == {}
        assert _candidates(CV_HANDWRITTEN) == {}


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
