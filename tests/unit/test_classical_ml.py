"""Classical ML: scikit-learn, XGBoost, LightGBM, and hand-written loops.

Every sample here is real output, captured by running the library rather than
written from memory of what it prints. The formats are fiddly in ways that are
easy to get wrong from imagination — LightGBM puts an apostrophe in its metric
name, XGBoost separates with tabs and names eval sets by position — and each of
those details is exactly what broke the parser before.

The failures this file pins are all the same shape: the log parses without
error, the dashboard renders, and what it says is untrue.
"""

from __future__ import annotations

import pytest

from epochix.enums import TaskType
from epochix.normalizer.canonical_keys import canonicalize_key
from epochix.parsers.base import ParserContext
from epochix.parsers.boosting import BoostingParser
from epochix.parsers.universal import UniversalParser
from epochix.story_engine.task_classifier import refine_gaze


def _parse(parser: object, lines: list[str]) -> list[tuple[str, float, float | None]]:
    ctx = ParserContext(run_id="test")
    out: list[tuple[str, float, float | None]] = []
    for line in lines:
        for m in parser.parse_line(line, ctx):  # type: ignore[attr-defined]
            out.append((m.key, m.value, m.epoch))
    return out


# ── Hand-written loops: no delimiter at all ────────────────────────────────


class TestWhitespaceSeparated:
    """`epoch 1 loss 0.68 acc 0.53` — the most common hand-rolled print.

    It produced NOTHING, while the extension's detector scored the same line
    0.90 and opened the dashboard. Detection and parsing have to agree, or the
    dashboard opens itself and sits empty.
    """

    def test_a_bare_loop_yields_its_metrics(self) -> None:
        got = _parse(UniversalParser(), ["epoch 1 loss 0.680 acc 0.535"])
        assert dict((k, v) for k, v, _ in got) == {"loss": 0.680, "acc": 0.535}

    def test_the_epoch_is_carried(self) -> None:
        got = _parse(UniversalParser(), ["epoch 7 loss 0.21 acc 0.94"])
        assert all(epoch == 7.0 for _, _, epoch in got), got

    def test_an_iteration_loop_gets_an_x_axis(self) -> None:
        """Real SGDRegressor output. Without this the story said "epoch ?"."""
        got = _parse(
            UniversalParser(),
            ["iter 1 rmse 15.2038 r2 0.9939", "iter 2 rmse 13.9910 r2 0.9948"],
        )
        assert [(k, e) for k, _, e in got] == [
            ("rmse", 1.0),
            ("r2", 1.0),
            ("rmse", 2.0),
            ("r2", 2.0),
        ]

    @pytest.mark.parametrize(
        "line",
        [
            "Done in 42.1s",
            "Train shape: (60000, 784)  Test shape: (10000, 784)",
            "Loading data from disk 3 files found",
            "Running 5-fold cross-validation...",
        ],
    )
    def test_prose_is_not_mined_for_metrics(self, line: str) -> None:
        """The guard that makes the above safe.

        A bare "word number" is also every sentence with a number in it.
        Inventing `in = 42.1` is worse than missing a metric, so the pattern
        only applies to a line that opens with a counter AND to names the
        normalizer recognises.
        """
        assert _parse(UniversalParser(), [line]) == []

    def test_a_counter_does_not_license_arbitrary_words(self) -> None:
        got = _parse(UniversalParser(), ["epoch 3 elapsed 12.5 workers 8 loss 0.4"])
        assert [k for k, _, _ in got] == ["loss"]


# ── Model configuration is not a measurement ───────────────────────────────


class TestEstimatorRepr:
    """`RandomForestClassifier(n_estimators=100)` charted 100 as a metric.

    It landed in the shared `custom` series next to a real F1 score, so a
    hyperparameter and a result were drawn as one line.
    """

    @pytest.mark.parametrize(
        "line",
        [
            "Fitting RandomForestClassifier(n_estimators=100, max_depth=8, random_state=0)",
            "GradientBoostingClassifier(learning_rate=0.1, max_depth=3)",
            "Ridge(alpha=1.0)",
            "XGBRegressor(n_estimators=40, max_depth=4, learning_rate=0.15)",
            "Conv2d(3, 64, kernel_size=(3, 3), stride=(1, 1))",
        ],
    )
    def test_constructor_kwargs_are_not_metrics(self, line: str) -> None:
        assert _parse(UniversalParser(), [line]) == []

    def test_a_real_metric_beside_a_repr_still_lands(self) -> None:
        got = _parse(UniversalParser(), ["Ridge(alpha=1.0) -> val_accuracy=0.91"])
        assert [(k, v) for k, v, _ in got] == [("val_accuracy", 0.91)]


# ── Train and test are not consecutive readings ────────────────────────────


class TestSplitQualifiers:
    def test_train_and_test_accuracy_are_separate_series(self) -> None:
        """Both were captured as `accuracy` and charted 1.0 -> 0.982.

        A decline the model never had: they measure different data.
        """
        got = _parse(
            UniversalParser(),
            ["Train accuracy: 1.0000", "Test accuracy: 0.9820"],
        )
        assert got == [("train_accuracy", 1.0, None), ("val_accuracy", 0.982, None)]

    def test_one_reading_is_recorded_once(self) -> None:
        """The qualified and bare patterns must not both claim the same text."""
        got = _parse(UniversalParser(), ["Test accuracy: 0.9820"])
        assert len(got) == 1, got

    def test_a_two_word_metric_name_survives(self) -> None:
        """ "F1 score: 0.98" was recorded as a metric called `score`."""
        got = _parse(UniversalParser(), ["F1 score: 0.9823", "R2 score: 0.87"])
        # The raw key keeps the case the user printed; canonicalisation is what
        # decides which series it joins.
        assert [k for k, _, _ in got] == ["F1_score", "R2_score"]
        assert [canonicalize_key(k) for k, _, _ in got] == ["f1", "R2"]


# ── Gradient boosting ──────────────────────────────────────────────────────


class TestBoosting:
    def test_xgboost_keeps_both_eval_sets(self) -> None:
        """Real XGBoost output, two eval sets.

        `\\w{1,64}` stopped at the `-`, so both columns were read as `logloss`
        and the second was dropped as a duplicate. One curve was charted and
        called the whole story — while the gap BETWEEN the curves is the
        overfitting signal the dashboard exists to show.
        """
        got = _parse(
            BoostingParser(),
            [
                "[0]\tvalidation_0-logloss:0.51987\tvalidation_1-logloss:0.52369",
                "[1]\tvalidation_0-logloss:0.40326\tvalidation_1-logloss:0.41045",
            ],
        )
        assert got == [
            ("train_logloss", 0.51987, 0.0),
            ("val_logloss", 0.52369, 0.0),
            ("train_logloss", 0.40326, 1.0),
            ("val_logloss", 0.41045, 1.0),
        ]

    def test_a_single_eval_set_is_validation(self) -> None:
        got = _parse(BoostingParser(), ["[7]\tvalidation_0-rmse:129.00216"])
        assert got == [("val_rmse", 129.00216, 7.0)]
        assert canonicalize_key("val_rmse") == "val_RMSE"

    def test_lightgbm_possessive_names(self) -> None:
        """`valid_0's l2` — an apostrophe and a space inside the metric name."""
        got = _parse(BoostingParser(), ["[2]\tvalid_0's l2: 30497.7"])
        assert got == [("val_l2", 30497.7, 2.0)]
        assert canonicalize_key("val_l2") == "val_MSE"

    def test_catboost_named_splits_are_taken_at_their_word(self) -> None:
        got = _parse(
            BoostingParser(),
            ["0:\tlearn: 0.6798710\ttest: 0.6801448\tbest: 0.6801448"],
        )
        # CatBoost names the split and not the objective, so the number is that
        # objective's value on that split — a loss. `best` is the running best
        # restated every row, not a measurement of this round: charting it
        # draws a staircase that can never worsen.
        assert [k for k, _, _ in got] == ["train_loss", "val_loss"]

    def test_the_round_is_the_x_axis(self) -> None:
        got = _parse(
            BoostingParser(), ["[0]\tvalidation_0-rmse:183.1", "[12]\tvalidation_0-rmse:99.2"]
        )
        assert [e for _, _, e in got] == [0.0, 12.0]

    def test_it_claims_boosting_logs_and_declines_others(self) -> None:
        parser = BoostingParser()
        boosting = [
            "[0]\tvalidation_0-logloss:0.51987",
            "[1]\tvalidation_0-logloss:0.40326",
            "[2]\tvalidation_0-logloss:0.31963",
        ]
        assert parser.sniff(boosting) >= 0.8
        assert parser.sniff(["Epoch 1/15 | train_loss: 0.58 | val_acc: 0.54"] * 3) == 0.0


# ── Vocabulary ─────────────────────────────────────────────────────────────


class TestCanonicalNames:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("logloss", "log_loss"),
            ("mlogloss", "log_loss"),
            ("binary_logloss", "log_loss"),
            ("l2", "MSE"),
            ("l1", "MAE"),
            ("merror", "error_rate"),
            ("r2_score", "R2"),
            ("mean_squared_error", "MSE"),
            ("balanced_accuracy", "balanced_accuracy"),
            ("matthews_corrcoef", "MCC"),
        ],
    )
    def test_classical_metric_names_are_recognised(self, raw: str, expected: str) -> None:
        """Each of these fell through to the shared `custom` bucket, where
        unrelated metrics are charted as one series."""
        assert canonicalize_key(raw) == expected

    @pytest.mark.parametrize(
        ("train_key", "val_key"),
        [("rmse", "val_rmse"), ("mse", "val_mse"), ("mae", "val_mae"), ("r2", "val_r2")],
    )
    def test_train_and_validation_error_do_not_collide(self, train_key: str, val_key: str) -> None:
        """These had no split form, so `val_rmse` was stripped to `rmse` and
        both splits were charted as one zig-zagging line."""
        assert canonicalize_key(train_key) != canonicalize_key(val_key)


# ── Gaze was invented from a number's size ─────────────────────────────────


class TestGazeIsNotGuessed:
    def test_ordinary_regression_stays_regression(self) -> None:
        """A real Ridge run reported MAE 9.83 and was relabelled a gaze model,
        narrated as "the model sees the face but not the gaze", with the value
        printed in degrees. A metric's magnitude cannot say what is predicted.
        """
        assert refine_gaze(TaskType.REGRESSION, 9.83, {"mae", "rmse", "r2"}) is TaskType.REGRESSION

    def test_a_named_gaze_metric_still_promotes(self) -> None:
        assert refine_gaze(TaskType.REGRESSION, 4.2, {"gaze_mae", "val_mae_deg"}) is TaskType.GAZE

    def test_a_gaze_name_with_an_implausible_error_does_not(self) -> None:
        assert refine_gaze(TaskType.REGRESSION, 340.0, {"gaze_mae"}) is TaskType.REGRESSION
