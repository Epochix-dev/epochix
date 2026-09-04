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
