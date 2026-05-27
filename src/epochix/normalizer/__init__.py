from __future__ import annotations

from datetime import datetime, timezone

from epochix.models import MetricEvent, RawMetric
from epochix.normalizer.canonical_keys import canonicalize_key
from epochix.normalizer.units import infer_unit


def normalize(raw: RawMetric, run_id: str, timestamp: datetime | None = None) -> MetricEvent:
    """Convert a RawMetric into a canonical MetricEvent."""
    if not isinstance(raw.value, (int, float)):
        raise ValueError(f"Cannot normalize non-numeric value: {raw.value!r}")

    canonical = canonicalize_key(raw.key)
    value = float(raw.value)
    unit = infer_unit(canonical, value)

    # Scale-normalise ratio metrics to [0, 1]. Frameworks log accuracy/mAP/EER
    # either as a fraction (0.876) or a percentage (87.6); downstream grading,
    # the skill radar and the diagnostics all assume a [0, 1] fraction, so a
    # %-unit value above 1 is treated as a percentage and divided by 100.
    if unit == "%" and value > 1.0:
        value = value / 100.0

    return MetricEvent(
        run_id=run_id,
        seq=raw.seq,
        timestamp=timestamp or datetime.now(tz=timezone.utc),
        epoch=raw.epoch,
        step=raw.step,
        canonical_key=canonical,
        raw_key=raw.key,
        value=value,
        unit=unit,
    )
