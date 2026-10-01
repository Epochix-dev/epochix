"""The pathology detector had no tests, and shipped unread for a long time.

Nothing rendered `store.warnings` in the dashboard until 0.7.5, so every one of
these detectors could have been silently broken and no one would have seen it.
These pin the four kinds it claims to find, and — as important — that a healthy
run trips none of them.

The divergence case in particular: a loss that doubles every epoch never
exceeds the single-step "10x the previous epoch" rule, so a run going
3.59 -> 2881 over eight epochs reported nothing at all. The `nan` branch could
not cover it either — the log parser's number pattern requires a digit, so a
literal `loss: nan` is never read and never reaches this class. Nor does the
SDK route around that: `LiveReporter.log` formats its kwargs into a text line
and feeds it to the same parsers. A NaN in a log is handled upstream, by the
pipeline sentinel in `tests/unit/test_diverged_nan.py`.
"""

from __future__ import annotations

from epochix.story_engine.warnings import WarningDetector


def _kinds(warnings: list) -> list[str]:
    return [w.kind for w in warnings]


class TestDivergence:
    def test_a_gradually_exploding_loss_is_reported(self) -> None:
        det = WarningDetector()
        fired: list[str] = []
        loss = 3.588
        for epoch in range(1, 9):
            fired += _kinds(det.update(epoch=epoch, train_loss=loss))
            loss *= 2.6
        assert "divergence" in fired, (
            "a loss growing 2.6x every epoch (3.59 -> 2881) reported nothing"
        )

    def test_a_single_huge_spike_is_still_reported(self) -> None:
        det = WarningDetector()
        det.update(epoch=1, train_loss=0.5)
        fired = _kinds(det.update(epoch=2, train_loss=500.0))
        assert "divergence" in fired

    def test_a_nan_loss_is_reported(self) -> None:
        """Only reachable by calling this class directly.

        Nothing in the product hands it a non-finite float. `LiveReporter.log`
        formats its kwargs into a text line and pushes that through the same
        parsers as a log file, and `MetricEvent.value` is a `FiniteFloat`, so a
        NaN never travels as a metric. A `loss: nan` line is caught earlier, by
        the pipeline's `_NON_FINITE_ASSIGNMENT` sentinel (see
        `tests/unit/test_diverged_nan.py`). Kept because the branch exists and
        an embedder calling the detector directly is entitled to it.
        """
        det = WarningDetector()
        det.update(epoch=1, train_loss=0.5)
        fired = _kinds(det.update(epoch=2, train_loss=float("nan")))
        assert "divergence" in fired

    def test_divergence_is_reported_once(self) -> None:
        det = WarningDetector()
        loss = 1.0
        fired: list[str] = []
        for epoch in range(1, 12):
            fired += _kinds(det.update(epoch=epoch, train_loss=loss))
            loss *= 3
        assert fired.count("divergence") == 1, f"repeated the same warning: {fired}"

    def test_a_normal_run_never_reports_divergence(self) -> None:
        det = WarningDetector()
        fired: list[str] = []
        for epoch in range(1, 21):
            fired += _kinds(det.update(epoch=epoch, train_loss=2.0 * 0.85**epoch))
        assert "divergence" not in fired

    def test_a_recovering_spike_does_not_report(self) -> None:
        """A loss that jumps 4x and comes back is noisy, not diverging."""
        det = WarningDetector()
        fired: list[str] = []
        for epoch, loss in enumerate([1.0, 0.8, 0.6, 2.4, 0.7, 0.5, 0.4], start=1):
            fired += _kinds(det.update(epoch=epoch, train_loss=loss))
        assert "divergence" not in fired, fired


class TestOverfit:
    def test_rising_val_with_falling_train_is_reported(self) -> None:
        det = WarningDetector()
        fired: list[str] = []
        for epoch in range(1, 9):
            fired += _kinds(
                det.update(
                    epoch=epoch,
                    train_loss=2.0 * 0.8**epoch,
                    val_loss=0.5 + 0.1 * epoch,
                )
            )
        assert "overfit" in fired

    def test_both_falling_is_not_overfitting(self) -> None:
        det = WarningDetector()
        fired: list[str] = []
        for epoch in range(1, 9):
            fired += _kinds(
                det.update(
                    epoch=epoch,
                    train_loss=2.0 * 0.8**epoch,
                    val_loss=2.1 * 0.82**epoch,
                )
            )
        assert "overfit" not in fired


class TestPlateau:
    def test_a_flat_primary_metric_is_reported(self) -> None:
        det = WarningDetector()
        fired: list[str] = []
        for epoch in range(1, 9):
            fired += _kinds(det.update(epoch=epoch, primary_value=0.700 + 0.0001 * epoch))
        assert "plateau" in fired

    def test_a_climbing_primary_metric_is_not_a_plateau(self) -> None:
        det = WarningDetector()
        fired: list[str] = []
        for epoch in range(1, 9):
            fired += _kinds(det.update(epoch=epoch, primary_value=0.4 + 0.05 * epoch))
        assert "plateau" not in fired


class TestLearningRate:
    def test_a_drop_is_reported_with_both_values(self) -> None:
        det = WarningDetector()
        det.update(epoch=1, lr=1e-3)
        fired = det.update(epoch=2, lr=1e-4)
        assert _kinds(fired) == ["lr_drop"]
        assert "1.00e-03" in fired[0].message and "1.00e-04" in fired[0].message

    def test_a_steady_rate_is_not_reported(self) -> None:
        det = WarningDetector()
        fired: list[str] = []
        for epoch in range(1, 6):
            fired += _kinds(det.update(epoch=epoch, lr=1e-3))
        assert fired == []


class TestHealthyRun:
    def test_a_good_run_trips_nothing(self) -> None:
        det = WarningDetector()
        fired: list[str] = []
        for epoch in range(1, 16):
            fired += _kinds(
                det.update(
                    epoch=epoch,
                    train_loss=2.3 * 0.80**epoch,
                    val_loss=2.3 * 0.82**epoch + 0.05,
                    primary_value=min(0.97, 0.35 + 0.045 * epoch),
                    lr=1e-3,
                )
            )
        assert fired == [], f"a healthy run was warned about: {fired}"


class TestOverfitWithdrawn:
    """A warm-up blip is not memorising.

    A real ResNet-18 on CIFAR-10 (tests/fixtures/logs/resnet18_cifar10.log)
    rose 0.862 -> 0.867 -> 1.229 in validation loss while the one-cycle
    learning rate climbed, set a new best at epoch 6 and fell to its lowest at
    epoch 30. The warning fired at epoch 5 and stood for the rest of the run,
    telling the reader to "stop at the best validation epoch" — epoch 30.
    """

    # train_loss, val_loss for epochs 1-8 of that run.
    RUN = [
        (1.5462, 1.3929),
        (1.0401, 0.9918),
        (0.8426, 0.8622),
        (0.6934, 0.8667),
        (0.6003, 1.2294),
        (0.5384, 0.6369),
        (0.4830, 0.6396),
        (0.4398, 0.5680),
    ]

    def _replay(self, rows: list[tuple[float, float]]) -> list[tuple[int, str]]:
        det = WarningDetector()
        fired: list[tuple[int, str]] = []
        for epoch, (train, val) in enumerate(rows, start=1):
            fired += [(epoch, k) for k in _kinds(det.update(epoch, train, val))]
        return fired

    def test_a_new_best_withdraws_the_warning(self) -> None:
        assert self._replay(self.RUN) == [(5, "overfit"), (6, "overfit_cleared")]

    def test_it_fires_again_if_the_run_overfits_later(self) -> None:
        later = [(0.40, 0.60), (0.38, 0.62), (0.36, 0.65)]
        # Epochs 8 -> 9 -> 10 rise (0.568, 0.60, 0.62) while training loss falls.
        assert self._replay(self.RUN + later) == [
            (5, "overfit"),
            (6, "overfit_cleared"),
            (10, "overfit"),
        ]

    def test_a_real_overfit_is_not_withdrawn(self) -> None:
        rows = [(1.0, 0.50), (0.8, 0.45), (0.6, 0.47), (0.4, 0.52), (0.3, 0.58), (0.2, 0.64)]
        assert self._replay(rows) == [(4, "overfit")]

    def test_the_withdrawal_is_in_every_language(self) -> None:
        from epochix.story_engine.messages import MESSAGES

        for locale, table in MESSAGES.items():
            assert table.get("warn_overfit_cleared"), locale


class TestPlateauWithdrawn:
    """The plateau warning describes the last five readings, so it stands only
    while it is true of them.

    A real Keras run (demo/keras_image_classifier.log) moved less than 1% over
    epochs 10-14, then climbed again. The banner kept saying the model "has
    stopped finding new patterns" beside a grade card reading "still improving
    at the last reading".
    """

    FLAT = [0.700, 0.701, 0.702, 0.703, 0.704]
    FLAT_AGAIN = [0.751, 0.752, 0.753, 0.754]

    def _replay(self, values: list[float]) -> list[tuple[int, str]]:
        det = WarningDetector()
        fired: list[tuple[int, str]] = []
        for epoch, value in enumerate(values, start=1):
            fired += [(epoch, k) for k in _kinds(det.update(epoch, primary_value=value))]
        return fired

    def test_a_metric_that_moves_again_withdraws_the_warning(self) -> None:
        assert self._replay([*self.FLAT, 0.75]) == [(5, "plateau"), (6, "plateau_cleared")]

    def test_it_fires_again_if_the_run_flattens_later(self) -> None:
        assert self._replay([*self.FLAT, 0.75, *self.FLAT_AGAIN]) == [
            (5, "plateau"),
            (6, "plateau_cleared"),
            (10, "plateau"),
        ]

    def test_a_run_that_stays_flat_keeps_its_one_warning(self) -> None:
        assert self._replay([0.700 + 0.0001 * e for e in range(1, 13)]) == [(5, "plateau")]

    def test_nothing_is_withdrawn_that_never_fired(self) -> None:
        assert self._replay([0.4 + 0.05 * e for e in range(1, 9)]) == []

    def test_the_withdrawal_is_in_every_language(self) -> None:
        from epochix.story_engine.messages import MESSAGES

        for locale, table in MESSAGES.items():
            assert table.get("warn_plateau_cleared"), locale


class TestTheWarningsStateWhatWasMeasured:
    """The sentences quote the detector's own numbers, so they cannot drift.

    "The model has stopped finding new patterns" was a conclusion; "moved less
    than 1% over the last 5 readings" is the measurement that fired it.
    """

    PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

    def _numbers(self, locale: str) -> tuple[str, str]:
        from epochix.story_engine import warnings as w

        percent = f"{w._PLATEAU_DELTA * 100:g}"
        window = str(w._PLATEAU_WINDOW)
        if locale == "fa":
            return (
                percent.translate(self.PERSIAN_DIGITS) + "٪",
                window.translate(self.PERSIAN_DIGITS),
            )
        return (percent + (" %" if locale == "fr" else "%"), window)

    def test_the_plateau_sentences_quote_the_window_and_the_threshold(self) -> None:
        from epochix.story_engine.messages import MESSAGES

        assert set(MESSAGES) == {"en", "fr", "fa"}, "a new locale needs its numbers checked"
        for locale, table in MESSAGES.items():
            percent, window = self._numbers(locale)
            for key in ("warn_plateau", "warn_plateau_cleared"):
                assert percent in table[key], (locale, key, percent)
                assert window in table[key], (locale, key, window)

    def test_the_overfit_sentence_counts_the_rises_the_detector_requires(self) -> None:
        from epochix.story_engine import warnings as w
        from epochix.story_engine.messages import MESSAGES

        # Three readings each above the last are two rises in a row.
        assert w._OVERFIT_WINDOW - 1 == 2
        two = {"en": "two readings in a row", "fr": "deux mesures de suite", "fa": "دو اندازه"}
        for locale, phrase in two.items():
            assert phrase in MESSAGES[locale]["warn_overfit"], locale

    def test_neither_warning_claims_more_than_it_measured(self) -> None:
        from epochix.story_engine.messages import MESSAGES

        english = MESSAGES["en"]
        assert "stopped finding" not in english["warn_plateau"]
        assert "unlikely to help" not in english["warn_plateau"]
        assert "may be memorising" in english["warn_overfit"]


class TestStandingWarnings:
    """What a report shows: the warnings no later reading withdrew."""

    def _warning(self, kind: str, message: str) -> object:
        from epochix.models import Warning

        return Warning(kind=kind, message=message)  # type: ignore[arg-type]

    def _standing(self, *pairs: tuple[str, str]) -> list[str]:
        from epochix.story_engine.warnings import standing_warnings

        return [w.kind for w in standing_warnings(self._warning(k, m) for k, m in pairs)]  # type: ignore[misc]

    def test_a_withdrawn_warning_and_its_withdrawal_are_both_gone(self) -> None:
        assert self._standing(("overfit", "a"), ("lr_drop", "b"), ("overfit_cleared", "c")) == [
            "lr_drop"
        ]

    def test_each_withdrawal_takes_only_its_own_kind(self) -> None:
        assert self._standing(("plateau", "a"), ("overfit", "b"), ("plateau_cleared", "c")) == [
            "overfit"
        ]

    def test_a_warning_that_fires_again_stands(self) -> None:
        assert self._standing(("plateau", "a"), ("plateau_cleared", "c"), ("plateau", "a")) == [
            "plateau"
        ]

    def test_the_same_message_is_listed_once(self) -> None:
        assert self._standing(("divergence", "a"), ("divergence", "a")) == ["divergence"]
