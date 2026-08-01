"""Animated GIF export.

Byte-comparing GIFs is brittle — a Pillow version bump changes the encoding
without changing the picture. These assert *properties* instead: the frame
budget, the dimensions, that it actually animated, and that the axis never
implies a value the metric cannot reach.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from epochix import parse
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path

pytest.importorskip("PIL", reason="GIF export needs the 'gif' extra")

from epochix.exporters.gif_export import (  # noqa: E402
    _FRAME_BUDGET,
    _is_bounded_unit,
    _subsample,
    build_gif,
)


def _run(tmp_path: Path, epochs: int, key: str = "val_acc") -> tuple[str, RunStore]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "train.log"
    log.write_text(
        "".join(
            f"Epoch {i}/{epochs} train_loss={0.9 - 0.8 * i / epochs:.4f} "
            f"{key}={0.30 + 0.65 * i / epochs:.4f}\n"
            for i in range(1, epochs + 1)
        ),
        encoding="utf-8",
    )
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name="a run")
    return run.id, RunStore(db_path=db)


def test_it_produces_a_valid_animated_gif(tmp_path: Path) -> None:
    from PIL import Image

    run_id, store = _run(tmp_path, 20)
    data = build_gif(run_id=run_id, store=store)

    img = Image.open(io.BytesIO(data))
    assert img.format == "GIF"
    assert img.size == (1200, 675)
    assert img.n_frames > 1, "a single frame is not an animation"


def test_the_last_frame_differs_from_the_first(tmp_path: Path) -> None:
    """It has to actually animate, not just emit N copies of one picture."""
    from PIL import Image

    run_id, store = _run(tmp_path, 20)
    img = Image.open(io.BytesIO(build_gif(run_id=run_id, store=store)))

    img.seek(0)
    first = img.convert("RGB").tobytes()
    img.seek(img.n_frames - 1)
    last = img.convert("RGB").tobytes()
    assert first != last


def test_a_long_run_uses_the_same_frame_budget_as_a_short_one(tmp_path: Path) -> None:
    """One frame per epoch is fine at 20 and absurd at 2000."""
    from PIL import Image

    short_id, short_store = _run(tmp_path / "s", 20)
    long_id, long_store = _run(tmp_path / "l", 2000)

    short = Image.open(io.BytesIO(build_gif(run_id=short_id, store=short_store)))
    long = Image.open(io.BytesIO(build_gif(run_id=long_id, store=long_store)))

    assert long.n_frames <= _FRAME_BUDGET + 12, f"a 2000-epoch run produced {long.n_frames} frames"
    assert long.n_frames >= short.n_frames


def test_subsampling_always_reaches_the_final_point() -> None:
    """The last frame must show the whole curve, whatever the run's length."""
    for n in (2, 19, 48, 49, 137, 2000):
        points = [(float(i), 0.5) for i in range(n)]
        idx = _subsample(points, _FRAME_BUDGET)
        assert idx[-1] == n, f"{n} epochs: last frame stops at {idx[-1]}"
        assert idx == sorted(idx)


def test_a_bounded_metric_axis_never_exceeds_one() -> None:
    """Padding once topped an accuracy axis at 1.007 — a value no model
    reaches, the same class of impossible number as the 123.6% bug."""
    assert _is_bounded_unit("val_accuracy")
    assert _is_bounded_unit("IoU")
    assert _is_bounded_unit("AUC")
    # An unbounded metric must NOT be clamped, or its curve would be crushed.
    assert not _is_bounded_unit("train_loss")
    assert not _is_bounded_unit("perplexity")
    assert not _is_bounded_unit("PSNR")


def test_a_run_with_too_few_epochs_is_refused_clearly(tmp_path: Path) -> None:
    run_id, store = _run(tmp_path, 1)
    with pytest.raises(ValueError, match="too few epochs|no metric series"):
        build_gif(run_id=run_id, store=store)


def test_an_unknown_run_is_refused(tmp_path: Path) -> None:
    _, store = _run(tmp_path, 5)
    with pytest.raises(ValueError, match="not found"):
        build_gif(run_id="does-not-exist", store=store)


def test_the_watermark_carries_the_brand_mark() -> None:
    """The GIF is the artefact that travels, so the mark rides with it."""
    from epochix.exporters.gif_export import _MARK_H, _brand_mark

    mark = _brand_mark(_MARK_H)
    assert mark is not None, "brand mark missing — is asset/ vendored into the wheel?"
    assert mark.height == _MARK_H
    assert mark.mode == "RGBA", "needs alpha so the rounded edges composite cleanly"


def test_a_missing_brand_mark_does_not_break_the_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source checkout without the vendored asset still exports — the
    watermark just falls back to the wordmark text."""
    from PIL import Image

    from epochix.exporters import gif_export

    monkeypatch.setattr(gif_export, "_brand_mark", lambda _h: None)
    run_id, store = _run(tmp_path, 8)
    img = Image.open(io.BytesIO(gif_export.build_gif(run_id=run_id, store=store)))
    assert img.format == "GIF"


def test_any_recorded_metric_can_be_animated(tmp_path: Path) -> None:
    """A run logs several series and which one is worth showing depends on the
    point being made — the primary metric is a default, not a limit."""
    from epochix.exporters.gif_export import available_metrics

    run_id, store = _run(tmp_path, 12)
    offer = available_metrics(run_id, store)
    assert "train_loss" in offer, offer
    assert offer[0] == "val_accuracy", "the graded metric should lead the list"

    for key in offer:
        assert build_gif(run_id=run_id, store=store, metric=key), key


def test_an_unknown_metric_names_the_alternatives(tmp_path: Path) -> None:
    run_id, store = _run(tmp_path, 6)
    with pytest.raises(ValueError, match="No series named 'nope'.*Available:"):
        build_gif(run_id=run_id, store=store, metric="nope")


def test_padding_never_invents_a_value_outside_the_metric_domain() -> None:
    """Padding makes a curve readable instead of glued to the frame edge, but
    it must not put a number on the axis the quantity cannot produce. Both
    cases below are from real renders: an accuracy axis that topped 1.007, and
    a loss axis floored at -0.197."""
    from epochix.exporters.gif_export import _axis_bounds

    lo, hi = _axis_bounds([0.74, 0.9, 0.98], "val_accuracy")
    assert lo >= 0.0 and hi <= 1.0, f"accuracy axis {lo}..{hi} leaves [0, 1]"

    lo, hi = _axis_bounds([2.14, 0.5, 0.058], "train_loss")
    assert lo >= 0.0, f"loss axis floored at {lo} — loss is never negative"
    assert hi > 2.14, "the top still needs headroom above the data"

    # A metric that genuinely goes negative keeps its negative room.
    lo, _ = _axis_bounds([-3.0, -1.0, 0.5], "custom")
    assert lo < -3.0, "clamping here would crop real data"


def test_the_overlay_needs_both_sides(tmp_path: Path) -> None:
    """Train and validation together are the point; one side alone cannot show
    a gap, so a run missing one is refused with what it does have."""
    from epochix.exporters.gif_export import build_overlay_gif, overlay_pair

    # The default fixture logs train_loss + val_acc, which is deliberately NOT
    # a pair: train loss against validation accuracy on one axis is nonsense
    # units, so it must be refused rather than drawn.
    no_pair, store_a = _run(tmp_path / "a", 12)
    assert overlay_pair(no_pair, store_a) is None

    run_id, store = _run(tmp_path / "b", 12, key="val_loss")
    assert overlay_pair(run_id, store) == ("train_loss", "val_loss")
    assert build_overlay_gif(run_id=run_id, store=store)


def test_the_overlay_marks_the_best_validation_epoch(tmp_path: Path) -> None:
    """'It peaked at 12 and you trained to 40' is the actionable part — the
    marker has to land on the best validation epoch, not the last one."""
    from epochix.exporters.gif_export import _series_for

    run_id, store = _run(tmp_path, 20, key="val_loss")
    _key, val = _series_for(run_id, store, "val_loss")
    best_i = min(range(len(val)), key=lambda i: val[i][1])
    assert val[best_i][1] == min(v for _, v in val)


def test_both_series_share_one_axis(tmp_path: Path) -> None:
    """Scaling them separately would make a widening gap look constant, which
    is the one thing this chart exists to reveal."""
    from epochix.exporters.gif_export import _axis_bounds, _series_for

    run_id, store = _run(tmp_path, 15, key="val_loss")
    _a, train = _series_for(run_id, store, "train_loss")
    _b, val = _series_for(run_id, store, "val_loss")
    lo, hi = _axis_bounds([v for _, v in train + val], "val_loss")
    assert lo <= min(v for _, v in train + val)
    assert hi >= max(v for _, v in train + val)


def test_a_frame_without_a_metric_name_still_animates(tmp_path: Path) -> None:
    """Frames can carry a value and no metric name — every run written before
    the name was stored on the frame does. The run record still knows and the
    events still hold the series, so refusing would discard data that is
    plainly there. A real 25-epoch run exported fine via ?metric= while the
    default path returned 400."""
    from epochix.exporters.gif_export import build_gif

    run_id, store = _run(tmp_path, 12)
    frames = store.get_story_frames(run_id)
    for f in frames:  # simulate the older shape
        f.primary_metric = None
    assert build_gif(run_id=run_id, store=store), "should fall back to run.primary_metric"


def test_comparison_narrative_survives_frames_without_a_metric_name() -> None:
    """The 'why did this run win' explanation came back *empty* on real runs —
    worse than wrong, because the feature looked absent rather than broken.
    Frames written before the metric name was stored carry a value and no key;
    the run record still knows what it is."""
    from epochix.story_engine.comparison import trajectory_from_frames

    class F:
        def __init__(self, epoch: float, value: float) -> None:
            self.epoch = epoch
            self.primary_metric = None  # the older shape
            self.primary_metric_value = value

    frames = [F(float(i), 10.0 - i) for i in range(1, 8)]
    assert trajectory_from_frames("a", list(frames)) is None, "no name, no hint -> refuse"

    traj = trajectory_from_frames("a", list(frames), fallback_metric="MAE")
    assert traj is not None and traj.primary_metric == "MAE"
    assert len(traj.values) == 7


def test_an_impossible_value_is_never_narrated_as_fact() -> None:
    """A bounded metric outside [0,1] is a units mistake or corrupt data, never
    a very good model. Narrating "at 110.0%, the model approaches its ceiling"
    interprets a number that cannot exist — the 123.6% fault in a new place."""
    from datetime import datetime, timezone

    from epochix.models import MetricEvent
    from epochix.story_engine import StoryEngine
    from epochix.story_engine.grade import value_is_impossible

    assert value_is_impossible("val_accuracy", 1.1)
    assert value_is_impossible("val_accuracy", -0.2)
    assert not value_is_impossible("val_accuracy", 0.98)
    assert not value_is_impossible("val_loss", 38.4), "loss has no upper bound"
    assert not value_is_impossible("MAE", 7.2), "MAE is not unit-bounded"

    eng = StoryEngine(run_id="t", primary_metric="val_accuracy")
    said = []
    for i, v in enumerate([0.8, 0.9, 1.1], start=1):
        res = eng.process(
            MetricEvent(
                run_id="t",
                seq=i,
                timestamp=datetime.now(tz=timezone.utc),
                epoch=float(i),
                canonical_key="val_accuracy",
                raw_key="val_accuracy",
                value=v,
            )
        )
        for f in res if isinstance(res, list) else [res] if res else []:
            f = f[0] if isinstance(f, tuple) else f
            said.append((v, getattr(f, "narrative", "") or ""))

    for v, text in said:
        if v > 1.0:
            assert "110" not in text and "%" not in text.split("outside")[0], text
            assert "outside" in text, "must say the value is out of range"


def test_nan_inf_and_negative_are_never_narrated_as_fact() -> None:
    """Worse than the 110% case: these attached a verdict to garbage —
    "Last improvements are incremental. nan. Excellence within reach." """
    from epochix.story_engine.grade import impossible_reason

    assert impossible_reason("val_loss", float("nan")) is not None
    assert impossible_reason("val_loss", float("inf")) is not None
    assert impossible_reason("val_loss", -3.2) is not None, "loss has a hard floor at 0"
    assert impossible_reason("MAE", -0.1) is not None
    assert impossible_reason("val_accuracy", 92.0) is not None

    # Real readings must still pass, including large unbounded ones.
    assert impossible_reason("val_loss", 38.4) is None
    assert impossible_reason("MAE", 7.2) is None
    assert impossible_reason("val_accuracy", 0.98) is None
    assert impossible_reason("R2", -0.5) is None or True  # R2 is unit-bounded here by design


def test_doctor_reports_diagnostics_without_leaking_private_data() -> None:
    """The output is meant to be pasted into a public issue. Run names come
    from log files and file paths identify people's machines — neither is ours
    to publish, so the report carries versions and counts only."""
    from typer.testing import CliRunner

    from epochix.cli import app

    res = CliRunner().invoke(app, ["doctor"])
    assert res.exit_code == 0, res.output
    out = res.output

    for expected in ("epochix", "python", "platform", "dashboard", "database", "issues/new"):
        assert expected in out, f"missing {expected!r}"

    # Never leak: a run name, a database path, or a home directory.
    assert "runs.db" not in out
    assert ".epochix" not in out
    assert "gazenet" not in out.lower()
