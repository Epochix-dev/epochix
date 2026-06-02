"""Normalizer unit tests."""

from __future__ import annotations

import pytest

from epochix.models import RawMetric
from epochix.normalizer import normalize
from epochix.normalizer.canonical_keys import canonicalize_key


class TestCanonicalKeys:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("val_acc", "val_accuracy"),
            ("accuracy", "accuracy"),
            ("loss", "train_loss"),
            ("valid_loss", "val_loss"),
            ("lr", "lr"),
            ("learning_rate", "lr"),
            ("mae", "MAE"),
            ("EER", "EER"),
            ("mAP50", "mAP50"),
            ("unknown_metric_xyz", "custom"),
        ],
    )
    def test_canonical_mapping(self, raw: str, expected: str) -> None:
        assert canonicalize_key(raw) == expected

    def test_case_insensitive(self) -> None:
        assert canonicalize_key("VAL_ACCURACY") == canonicalize_key("val_accuracy")


class TestNormalize:
    def _raw(self, key: str, value: float) -> RawMetric:
        return RawMetric(seq=1, key=key, value=value, parser_name="test", confidence=0.9)

    def test_produces_metric_event(self) -> None:
        raw = self._raw("val_acc", 0.85)
        event = normalize(raw, run_id="run-1")
        assert event.canonical_key == "val_accuracy"
        assert event.value == 0.85
        assert event.run_id == "run-1"

    def test_percentage_accuracy_normalised_to_fraction(self) -> None:
        # Logged as a percentage (87.6) → stored as a [0,1] fraction.
        event = normalize(self._raw("accuracy", 87.6), run_id="run-1")
        assert event.value == pytest.approx(0.876)

    def test_fractional_accuracy_left_unchanged(self) -> None:
        event = normalize(self._raw("accuracy", 0.876), run_id="run-1")
        assert event.value == pytest.approx(0.876)

    def test_non_ratio_metric_not_rescaled(self) -> None:
        # Loss is unitless and may legitimately exceed 1 — must not be divided.
        event = normalize(self._raw("loss", 2.5), run_id="run-1")
        assert event.value == pytest.approx(2.5)

    def test_raises_on_non_numeric(self) -> None:
        raw = RawMetric(seq=1, key="status", value="running", parser_name="test", confidence=0.5)
        with pytest.raises(ValueError):
            normalize(raw, run_id="run-1")
