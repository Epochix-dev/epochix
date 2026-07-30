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
