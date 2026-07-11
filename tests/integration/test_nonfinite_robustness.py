"""A diverged run logging NaN / ±Inf must never crash the pipeline, the store,
or JSON serialisation (Starlette 500s on non-finite floats; browsers reject the
NaN/Infinity JSON tokens). Non-finite values are dropped at the normalizer;
the WS/API serialisers null out anything non-finite as defence in depth."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest

from epochix.enums import Grade, Phase, TaskType
from epochix.models import RawLogLine, RawMetric, StoryFrame
from epochix.normalizer import normalize
from epochix.server.hub import Hub
from epochix.server.jsonsafe import SafeJSONResponse, sanitize_nonfinite, ws_json
from epochix.store.sqlite_store import RunStore


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_normalizer_drops_non_finite(bad: float) -> None:
    raw = RawMetric(seq=1, epoch=1.0, key="val_loss", value=bad, parser_name="p", confidence=1.0)
    with pytest.raises(ValueError, match="non-finite"):
        normalize(raw, run_id="r")


def test_sanitize_nonfinite_recurses() -> None:
    out = sanitize_nonfinite(
        {"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": float("-inf")}, "e": 2.0}
    )
    assert out == {"a": None, "b": [1.0, None], "c": {"d": None}, "e": 2.0}
    json.dumps(out, allow_nan=False)  # must be strict-valid JSON


def test_ws_json_nulls_non_finite_frame() -> None:
    frame = StoryFrame(
        run_id="r",
        seq=1,
        epoch=1.0,
        progress=0.5,
        phase=Phase.LEARNING,
        grade=Grade.C,
        primary_metric_value=float("nan"),
        confidence=0.5,
        narrative="x",
        task_type=TaskType.CLASSIFICATION,
        skill_dimensions={"Val Accuracy": float("inf")},
    )
    msg = Hub.make_message(
        msg_type="story_frame", run_id="r", seq=1, payload=frame.model_dump(mode="json")
    )
    text = ws_json(msg)
    parsed = json.loads(text)  # strict parse — raises on NaN/Infinity tokens
    assert parsed["payload"]["primary_metric_value"] is None
    assert parsed["payload"]["skill_dimensions"]["Val Accuracy"] is None


def test_safe_json_response_never_raises() -> None:
    body = SafeJSONResponse({"v": float("nan"), "xs": [float("inf"), 1.0]}).body
    assert json.loads(body) == {"v": None, "xs": [None, 1.0]}


class _NaNIngester:
    """Feeds a real gaze run whose middle epoch diverges to NaN/Inf."""

    async def lines(self) -> AsyncIterator[RawLogLine]:
        rows = [
            "epoch=1 train_loss=15.2 val_loss=52.1 val_mae_cm=9.8",
            "epoch=2 train_loss=nan val_loss=inf val_mae_cm=nan",  # diverged epoch
            "epoch=3 train_loss=12.4 val_loss=49.1 val_mae_cm=8.9",
            "epoch=4 train_loss=11.7 val_loss=48.5 val_mae_cm=8.6",
        ]
        for i, text in enumerate(rows, start=1):
            yield RawLogLine(
                seq=i, timestamp=datetime.now(tz=timezone.utc), text=text, source="stdin"
            )


async def test_pipeline_survives_diverged_epoch() -> None:
    import epochix.pipeline as pipeline

    store = RunStore(":memory:")
    hub = Hub()
    await pipeline.run_pipeline(
        ingester=_NaNIngester(),
        run_id="div",
        store=store,
        hub=hub,
        task=None,
        primary_metric="val_mae_cm",
    )
    frames = store.get_story_frames("div")
    assert len(frames) > 0, "no frames from a run with one diverged epoch"
    # Every stored/served value is finite — the NaN epoch was dropped, not stored.
    for f in frames:
        payload = f.model_dump(mode="json")
        json.dumps(payload, allow_nan=False)  # strict-valid
        assert f.primary_metric_value is None or f.primary_metric_value == f.primary_metric_value
    for e in store.get_metric_events("div"):
        assert e.value == e.value  # not NaN
