from __future__ import annotations

from datetime import datetime, timezone

from model_story.models import MetricEvent, RawMetric
from model_story.normalizer.canonical_keys import canonicalize_key
from model_story.normalizer.units import infer_unit


def normalize(raw: RawMetric, run_id: str, timestamp: datetime | None = None) -> MetricEvent:
    """Convert a RawMetric into a canonical MetricEvent."""
    if not isinstance(raw.value, (int, float)):
        raise ValueError(f"Cannot normalize non-numeric value: {raw.value!r}")

    canonical = canonicalize_key(raw.key)
    value = float(raw.value)
    unit = infer_unit(canonical, value)

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
