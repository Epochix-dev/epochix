"""Animated GIF of a run's learning curve — the shareable artefact.

Rendered **server-side with Pillow**, deliberately. Capturing the live canvas
would make the CLI depend on a headless browser at runtime: slow, fragile in
CI, and impossible on a machine with no display. Drawing the frames directly
costs a few hundred lines and runs anywhere the package runs.

Two constraints shape the design:

* **GIF has a 256-colour palette.** The dashboard's gradients band badly when
  quantised, so this uses a flat theme with a handful of solid colours. That
  also reads better at the size these are actually viewed.
* **The last frame is the product.** Most platforms show it as the still
  preview, so it carries the grade, the metric and the run name on its own.

Ships behind the ``gif`` extra: ``pip install 'epochix[gif]'``.
"""

from __future__ import annotations

import io
import math
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from epochix.store.sqlite_store import RunStore

# A run of any length is squeezed into this many frames. Animating one frame
# per epoch is fine at 20 epochs and absurd at 2000 — a fixed budget keeps
# every export roughly the same length.
_FRAME_BUDGET = 48
_HOLD_FRAMES = 9  # ~1.5 s on the final frame, so it can actually be read
_FPS = 6

_W, _H = 1200, 675  # 16:9 — embeds cleanly and is legible as a thumbnail

# Hard bounds on anything a caller can set. `build_gif` is a public function and
# will be reachable over HTTP once the dashboard's Record button lands, so a
# caller-supplied size must never decide how much memory we allocate:
# 20000x20000 is 1.2 GB *per frame*, and there are dozens of frames.
_MIN_DIM, _MAX_DIM = 320, 2400
_MAX_FPS = 30

# A run name comes from a log file, which is untrusted input. Drawing 100k
# characters is not a crash but it is free CPU for an attacker, and the excess
# renders off-canvas where nobody sees it anyway.
_MAX_NAME_CHARS = 80

# Watermark mark height. Small enough to stay a signature, large enough to be
# recognisable when the GIF is scaled down to a timeline thumbnail.
_MARK_H = 20
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 96, 56, 132, 88

# Flat palette: no gradients, so the 256-colour quantisation has nothing to
# band. Chosen for contrast at thumbnail size rather than for screen beauty.
_BG = (11, 14, 26)
_INK = (232, 236, 248)
_MUTED = (128, 138, 168)
_GRID = (32, 38, 60)
_LINE = (94, 174, 255)
_ACCENT = (124, 109, 255)


def _require_pillow() -> Any:  # noqa: ANN401 - optional dep, no stubs at type-check time
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - exercised via the CLI
        raise NotImplementedError(
            "GIF export needs the 'gif' extra: pip install 'epochix[gif]'"
        ) from exc
    return Image, ImageDraw


def _subsample(points: list[tuple[float, float]], budget: int) -> list[int]:
    """Indices to draw up to, one per animation frame.

    Always ends on the last point, so the final frame shows the whole curve
    however long the run was.
    """
    if len(points) <= budget:
        return list(range(1, len(points) + 1))
    step = len(points) / budget
    idx = sorted({max(1, round((i + 1) * step)) for i in range(budget)})
    if idx[-1] != len(points):
        idx.append(len(points))
    return idx


# Metrics that live in [0, 1] by construction. Their axis must never imply a
# value outside that range.
_UNIT_METRICS = frozenset(
    {
        "accuracy",
        "val_accuracy",
        "train_accuracy",
        "top5_accuracy",
        "AUC",
        "PR_AUC",
        "f1",
        "precision",
        "recall",
        "specificity",
        "IoU",
        "mIoU",
        "Dice",
        "pixel_accuracy",
        "mAP",
        "mAP50",
        "mAP75",
        "SSIM",
        "R2",
        "TAR",
        "EER",
        "NDCG",
        "MRR",
    }
)


def _is_bounded_unit(metric: str) -> bool:
    return metric in _UNIT_METRICS


def _axis_bounds(ys: list[float], metric: str) -> tuple[float, float]:
    """Padded y-axis range that never implies a value the metric cannot take.

    Padding is what makes a curve readable instead of glued to the frame edge,
    but it must not invent numbers outside the metric's domain. Two guards,
    both from real renders:

    * A bounded metric got an axis topping **1.007** — no model reaches that.
    * A loss curve got a floor of **-0.197** — no loss, error or perplexity
      value is negative.

    Both are the same fault as the 123.6% this project shipped once: a number
    on screen that the quantity behind it cannot produce.
    """
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or (abs(hi) or 1.0)
    lo -= span * 0.12
    hi += span * 0.12
    if _is_bounded_unit(metric):
        lo, hi = max(lo, 0.0), min(hi, 1.0)
    if min(ys) >= 0.0:
        lo = max(lo, 0.0)
    return lo, hi


def _safe_label(text: str) -> str:
    """Make a log-derived string safe to draw.

    Control characters and bidi overrides can reorder or hide what a reader
    sees — a name like "safe‮gnp.exe" displays reversed. Strip the
    formatting classes, collapse whitespace, and cap the length.
    """
    cleaned = "".join(
        " " if ch in "\r\n\t" else ch for ch in text if unicodedata.category(ch) not in {"Cc", "Cf"}
    )
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > _MAX_NAME_CHARS:
        cleaned = cleaned[: _MAX_NAME_CHARS - 1] + "…"
    return cleaned or "run"


def _brand_mark(height: int) -> Any | None:  # noqa: ANN401 - PIL image, optional dep
    """The Epochix mark, scaled to *height* px, or None if it is unavailable.

    Vendored into the wheel as ``epochix/_brand/mark.png`` (see the
    force-include in pyproject). A source checkout that lacks it — or a mark
    that fails to decode — must not break the export: the watermark falls back
    to the wordmark text alone.
    """
    from PIL import Image

    path = Path(__file__).resolve().parents[1] / "_brand" / "mark.png"
    if not path.is_file():
        return None
    try:
        mark = Image.open(path).convert("RGBA")
    except OSError:  # pragma: no cover - corrupt or unreadable asset
        return None
    w = max(1, round(mark.width * height / mark.height))
    # Image.Resampling, not the bare Image.LANCZOS alias: the alias still works
    # at runtime but is absent from Pillow's type stubs, so mypy --strict
    # rejects it. The `gif` extra floors at Pillow 10, which has Resampling.
    return mark.resize((w, height), Image.Resampling.LANCZOS)


def _font(size: int) -> Any:  # noqa: ANN401 - PIL font object, optional dep
    from PIL import ImageFont

    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def available_metrics(run_id: str, store: RunStore) -> list[str]:
    """Series in this run that can be animated, best-known first.

    The primary metric leads because it is what the story is graded on; the
    rest follow alphabetically. Callers use this to offer a choice and to say
    what went wrong when an unknown metric is asked for.
    """
    keys = {e.canonical_key for e in store.get_metric_events(run_id) if e.epoch is not None}
    run = store.get_run(run_id)
    primary = run.primary_metric if run else None
    rest = sorted(keys - {primary})
    return ([primary] if primary in keys else []) + rest


def _series_for(
    run_id: str, store: RunStore, metric: str | None
) -> tuple[str, list[tuple[float, float]]]:
    """The (metric_name, points) a run should be drawn from.

    A named metric is read from the raw events, which hold every series the run
    recorded. Without one, the primary metric is taken from the story frames —
    frames carry only that series, which is exactly why a named metric cannot
    come from them.
    """
    if metric:
        points = [
            (float(e.epoch), float(e.value))
            for e in store.get_metric_events(run_id)
            if e.canonical_key == metric and e.epoch is not None
        ]
        if not points:
            offer = available_metrics(run_id, store)
            raise ValueError(
                f"No series named {metric!r} in this run. "
                + (f"Available: {', '.join(offer)}." if offer else "This run recorded none.")
            )
    else:
        frames = store.get_story_frames(run_id)
        # One metric only: an early frame can predate task detection and
        # measure something else, and joining a loss to an accuracy would be a
        # false curve.
        counts: dict[str, int] = {}
        for f in frames:
            if f.primary_metric and f.primary_metric_value is not None:
                counts[f.primary_metric] = counts.get(f.primary_metric, 0) + 1
        if not counts:
            raise ValueError("This run has no metric series to animate.")
        metric = max(counts, key=lambda k: counts[k])
        points = [
            (float(f.epoch), float(f.primary_metric_value))
            for f in frames
            if f.primary_metric == metric and f.epoch is not None
        ]
    # A diverged run stores NaN/Inf; they would propagate into pixel
    # coordinates and hang or crash the rasteriser.
    points = [(e, v) for e, v in points if math.isfinite(e) and math.isfinite(v)]
    points.sort(key=lambda ev: ev[0])
    return metric, points


def build_gif(
    run_id: str,
    store: RunStore,
    *,
    metric: str | None = None,
    fps: int = _FPS,
    width: int = _W,
    height: int = _H,
) -> bytes:
    """Render a metric curve as an animated GIF.

    *metric* selects which series to animate — any canonical key the run
    recorded, not only the primary one. A training run logs several (loss,
    accuracy, learning rate) and which of them is worth showing depends on the
    point being made, so the choice belongs to the caller. Defaults to the
    primary metric, which is what the run is graded on.
    """
    Image, ImageDraw = _require_pillow()

    # Clamp before allocating anything.
    width = max(_MIN_DIM, min(int(width), _MAX_DIM))
    height = max(_MIN_DIM, min(int(height), _MAX_DIM))
    fps = max(1, min(int(fps), _MAX_FPS))

    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id!r}")

    metric, points = _series_for(run_id, store, metric)
    if len(points) < 2:
        raise ValueError("This run has too few epochs to animate.")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    lo, hi = _axis_bounds(ys, metric)
    x0, x1 = min(xs), max(xs)

    plot_w = width - _PAD_L - _PAD_R
    plot_h = height - _PAD_T - _PAD_B

    def px(epoch: float) -> float:
        return _PAD_L + (epoch - x0) / ((x1 - x0) or 1.0) * plot_w

    def py(value: float) -> float:
        return _PAD_T + (1 - (value - lo) / (hi - lo)) * plot_h

    title_font, label_font, big_font, small_font = (
        _font(34),
        _font(20),
        _font(62),
        _font(17),
    )
    grade = run.final_grade.value if run.final_grade else "—"
    name = _safe_label(run.name or run_id)
    # Decoded and scaled once, not per frame — there are ~48 of them.
    mark = _brand_mark(_MARK_H)

    images: list[Any] = []
    for upto in _subsample(points, _FRAME_BUDGET):
        img = Image.new("RGB", (width, height), _BG)
        d = ImageDraw.Draw(img)

        for i in range(5):  # horizontal gridlines
            y = _PAD_T + i * plot_h / 4
            d.line([(_PAD_L, y), (width - _PAD_R, y)], fill=_GRID, width=1)
            d.text(
                (_PAD_L - 14, y - 10),
                f"{hi - i * (hi - lo) / 4:.3f}",
                font=small_font,
                fill=_MUTED,
                anchor="ra",
            )

        d.text((_PAD_L, 42), name, font=title_font, fill=_INK)
        d.text((_PAD_L, 86), metric, font=label_font, fill=_MUTED)

        drawn = points[:upto]
        if len(drawn) >= 2:
            d.line(
                [(px(e), py(v)) for e, v in drawn],
                fill=_LINE,
                width=5,
                joint="curve",
            )
        e, v = drawn[-1]
        d.ellipse([px(e) - 8, py(v) - 8, px(e) + 8, py(v) + 8], fill=_ACCENT)

        d.text(
            (width - _PAD_R, 40),
            f"{v:.4f}",
            font=title_font,
            fill=_INK,
            anchor="ra",
        )
        d.text(
            (width - _PAD_R, 84),
            f"epoch {int(e)} of {int(x1)}",
            font=label_font,
            fill=_MUTED,
            anchor="ra",
        )
        d.line(
            [(_PAD_L, height - _PAD_B), (width - _PAD_R, height - _PAD_B)],
            fill=_GRID,
            width=2,
        )
        # The URL is the point: this file travels, and it is the only thing
        # that turns a viewer into a visitor. The mark sits to its left so the
        # pair reads as one lockup rather than two stray marks in a corner.
        wm_y = height - 40
        d.text((width - _PAD_R, wm_y), "epochix.dev", font=small_font, fill=_MUTED, anchor="ra")
        if mark is not None:
            text_w = d.textlength("epochix.dev", font=small_font)
            img.paste(
                mark,
                (int(width - _PAD_R - text_w - mark.width - 8), wm_y - 3),
                mark,  # its own alpha, so the rounded edges stay clean
            )

        # Grade appears only once the curve is complete — it is the run's
        # verdict, not a running commentary.
        if upto == len(points):
            d.text((_PAD_L, height - 74), grade, font=big_font, fill=_ACCENT)
            d.text((_PAD_L + 96, height - 44), "final grade", font=small_font, fill=_MUTED)

        images.append(img)

    images.extend([images[-1]] * _HOLD_FRAMES)

    buf = io.BytesIO()
    images[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=int(1000 / max(fps, 1)),
        loop=0,
        optimize=True,
    )
    return buf.getvalue()


# Distinct at thumbnail size and after 256-colour quantisation. Ordered so the
# first two — the common case, a baseline against one change — are furthest
# apart, and chosen to stay distinguishable in the most common colour blindness
# (deuteranopia): the pairs differ in lightness, not only in hue.
_RACE_COLOURS = [
    (94, 174, 255),  # blue
    (255, 176, 59),  # amber
    (124, 109, 255),  # violet
    (46, 204, 158),  # teal
    (244, 114, 182),  # pink
    (163, 230, 53),  # lime
]

# Each run multiplies the render cost, and a legend stops being readable long
# before this. Six is a comparison; twenty is a mess.
_MAX_RACE_RUNS = 6


def build_comparison_gif(
    run_ids: list[str],
    store: RunStore,
    *,
    metric: str | None = None,
    fps: int = _FPS,
    width: int = _W,
    height: int = _H,
) -> bytes:
    """Animate several runs advancing together — the version for a slide.

    Curves are aligned **by epoch**, not by frame index. Runs of different
    lengths therefore finish at different moments, which is the honest picture:
    a run that reached 0.95 in 8 epochs did not do the same thing as one that
    took 40, and normalising the x-axis would hide precisely that.

    Every run must be able to supply the same metric. Drawing one run's
    accuracy beside another's loss would be a chart that invites exactly the
    wrong conclusion, so a run missing the series is refused by name rather
    than quietly dropped.
    """
    Image, ImageDraw = _require_pillow()

    width = max(_MIN_DIM, min(int(width), _MAX_DIM))
    height = max(_MIN_DIM, min(int(height), _MAX_DIM))
    fps = max(1, min(int(fps), _MAX_FPS))

    if len(run_ids) < 2:
        raise ValueError("A comparison needs at least two runs.")
    if len(run_ids) > _MAX_RACE_RUNS:
        raise ValueError(f"At most {_MAX_RACE_RUNS} runs can race; {len(run_ids)} were given.")

    runs = []
    for rid in run_ids:
        run = store.get_run(rid)
        if run is None:
            raise ValueError(f"Run not found: {rid!r}")
        runs.append(run)

    # Settle the metric before reading any series, so the failure names the
    # disagreement rather than the first run that happens to lack the key.
    if metric is None:
        commons = [set(available_metrics(r.id, store)) for r in runs]
        shared = set.intersection(*commons) if commons else set()
        preferred = [r.primary_metric for r in runs if r.primary_metric in shared]
        if not shared:
            raise ValueError("These runs share no metric, so there is nothing to compare them on.")
        metric = preferred[0] if preferred else sorted(shared)[0]

    series: list[tuple[str, list[tuple[float, float]]]] = []
    for run in runs:
        _key, points = _series_for(run.id, store, metric)
        if len(points) < 2:
            raise ValueError(f"{run.name or run.id!r} has too few {metric} points to animate.")
        series.append((_safe_label(run.name or run.id), points))

    all_ys = [v for _, pts in series for _, v in pts]
    all_xs = [e for _, pts in series for e, _ in pts]
    lo, hi = _axis_bounds(all_ys, metric)
    x0, x1 = min(all_xs), max(all_xs)

    plot_w = width - _PAD_L - _PAD_R
    plot_h = height - _PAD_T - _PAD_B

    def px(epoch: float) -> float:
        return _PAD_L + (epoch - x0) / ((x1 - x0) or 1.0) * plot_w

    def py(value: float) -> float:
        return _PAD_T + (1 - (value - lo) / ((hi - lo) or 1.0)) * plot_h

    title_font, label_font, small_font = _font(34), _font(20), _font(17)
    mark = _brand_mark(_MARK_H)

    # Where do the curves finish? Accuracy climbs into the top-right; loss
    # falls into the bottom-right. The legend takes the other corner.
    finals = [pts[-1][1] for _, pts in series]
    ends_low = (sum(finals) / len(finals)) < (lo + hi) / 2

    # One frame per step along the shared epoch axis, budget-capped exactly as
    # the single-run export is: length must not scale with the longest run.
    epoch_stops = sorted({e for _, pts in series for e, _ in pts})
    stops = [epoch_stops[i - 1] for i in _subsample([(e, 0.0) for e in epoch_stops], _FRAME_BUDGET)]

    images: list[Any] = []
    for cutoff in stops:
        img = Image.new("RGB", (width, height), _BG)
        d = ImageDraw.Draw(img)

        for i in range(5):
            y = _PAD_T + i * plot_h / 4
            d.line([(_PAD_L, y), (width - _PAD_R, y)], fill=_GRID, width=1)
            d.text(
                (_PAD_L - 14, y - 10),
                f"{hi - i * (hi - lo) / 4:.3f}",
                font=small_font,
                fill=_MUTED,
                anchor="ra",
            )

        d.text((_PAD_L, 42), f"{len(series)} runs compared", font=title_font, fill=_INK)
        d.text((_PAD_L, 86), metric, font=label_font, fill=_MUTED)
        d.text(
            (width - _PAD_R, 86),
            f"epoch {int(cutoff)} of {int(x1)}",
            font=label_font,
            fill=_MUTED,
            anchor="ra",
        )

        reached_at: list[str] = []
        for idx, (_name, pts) in enumerate(series):
            colour = _RACE_COLOURS[idx % len(_RACE_COLOURS)]
            drawn = [(e, v) for e, v in pts if e <= cutoff]
            if len(drawn) >= 2:
                d.line([(px(e), py(v)) for e, v in drawn], fill=colour, width=4, joint="curve")
            if drawn:
                e, v = drawn[-1]
                d.ellipse([px(e) - 6, py(v) - 6, px(e) + 6, py(v) + 6], fill=colour)
            reached_at.append(f"{drawn[-1][1]:.4f}" if drawn else "—")

        # Legend last, over an opaque panel: every part of the plot is fair
        # game for a curve, so there is no corner where text is safe. Drawing
        # it before the lines left one running straight through the labels.
        #
        # And it goes wherever the curves are not. Pinned top-right it sat on
        # top of the endpoints of the two leading runs — hiding the finish of
        # the very thing being compared. Rising metrics end high, falling ones
        # end low, so the free corner is decided from the data.
        legend_top = 118 if ends_low else height - _PAD_B - len(series) * 26 - 30
        d.rectangle(
            [
                width - _PAD_R - 220,
                legend_top,
                width - _PAD_R + 6,
                legend_top + len(series) * 26 + 8,
            ],
            fill=_BG,
            outline=_GRID,
        )
        for idx, (name, _pts) in enumerate(series):
            colour = _RACE_COLOURS[idx % len(_RACE_COLOURS)]
            # A scoreboard, not a key: the value each run has reached *at this
            # point in the animation*, which is what makes it a race.
            ly = legend_top + 14 + idx * 26
            d.line([(width - _PAD_R - 210, ly), (width - _PAD_R - 186, ly)], fill=colour, width=4)
            reached = reached_at[idx]
            # Trim to the space actually left after the value, measured rather
            # than a fixed character count. Two real runs both named
            # "gazenet-gazecapture-24subj" truncated to 22 characters and ran
            # straight through their own scores — a fixed count cannot know how
            # wide a glyph is.
            name_x = width - _PAD_R - 178
            room = (width - _PAD_R) - d.textlength(reached, font=small_font) - 10 - name_x
            label = name
            while label and d.textlength(label, font=small_font) > room:
                label = label[:-1]
            if label != name and len(label) > 1:
                label = label[:-1] + "…"
            d.text((name_x, ly - 9), label, font=small_font, fill=_INK)
            d.text((width - _PAD_R, ly - 9), reached, font=small_font, fill=_MUTED, anchor="ra")

        d.line([(_PAD_L, height - _PAD_B), (width - _PAD_R, height - _PAD_B)], fill=_GRID, width=2)
        wm_y = height - 40
        d.text((width - _PAD_R, wm_y), "epochix.dev", font=small_font, fill=_MUTED, anchor="ra")
        if mark is not None:
            text_w = d.textlength("epochix.dev", font=small_font)
            img.paste(mark, (int(width - _PAD_R - text_w - mark.width - 8), wm_y - 3), mark)

        images.append(img)

    images.extend([images[-1]] * _HOLD_FRAMES)

    buf = io.BytesIO()
    images[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=int(1000 / max(fps, 1)),
        loop=0,
        optimize=True,
    )
    return buf.getvalue()


# Train/validation pairs, best first. A chart that puts these two side by side
# answers the question people most often want a picture of — did it overfit —
# which no single curve can show.
_OVERLAY_PAIRS = [
    ("train_loss", "val_loss"),
    ("accuracy", "val_accuracy"),
]


def overlay_pair(run_id: str, store: RunStore) -> tuple[str, str] | None:
    """The (train, val) pair this run can overlay, or None if it logged only one side."""
    keys = {e.canonical_key for e in store.get_metric_events(run_id) if e.epoch is not None}
    for train, val in _OVERLAY_PAIRS:
        if train in keys and val in keys:
            return (train, val)
    return None


def build_overlay_gif(
    run_id: str,
    store: RunStore,
    *,
    fps: int = _FPS,
    width: int = _W,
    height: int = _H,
) -> bytes:
    """Train and validation on one axis, with the best-validation epoch marked.

    The gap between these two curves *is* overfitting, and a single-metric chart
    cannot show it however carefully it is drawn. The marker sits on the best
    validation epoch — the checkpoint worth keeping — because "it peaked at 12
    and you trained to 40" is the actionable part, not the final number.

    Both series share one axis deliberately. Scaling them separately would make
    a widening gap look constant, which is the one thing this chart exists to
    reveal.
    """
    Image, ImageDraw = _require_pillow()

    width = max(_MIN_DIM, min(int(width), _MAX_DIM))
    height = max(_MIN_DIM, min(int(height), _MAX_DIM))
    fps = max(1, min(int(fps), _MAX_FPS))

    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id!r}")

    pair = overlay_pair(run_id, store)
    if pair is None:
        raise ValueError(
            "This run has no train/validation pair to overlay — it logged only one side. "
            f"Available: {', '.join(available_metrics(run_id, store)) or 'none'}."
        )
    train_key, val_key = pair
    _t, train_pts = _series_for(run_id, store, train_key)
    _v, val_pts = _series_for(run_id, store, val_key)
    if len(train_pts) < 2 or len(val_pts) < 2:
        raise ValueError("Too few epochs to animate.")

    lower_better = "loss" in val_key
    best_i = (min if lower_better else max)(range(len(val_pts)), key=lambda i: val_pts[i][1])
    best_epoch, best_val = val_pts[best_i]

    lo, hi = _axis_bounds([v for _, v in train_pts + val_pts], val_key)
    xs = [e for e, _ in train_pts + val_pts]
    x0, x1 = min(xs), max(xs)
    plot_w, plot_h = width - _PAD_L - _PAD_R, height - _PAD_T - _PAD_B

    def px(e: float) -> float:
        return _PAD_L + (e - x0) / ((x1 - x0) or 1.0) * plot_w

    def py(v: float) -> float:
        return _PAD_T + (1 - (v - lo) / ((hi - lo) or 1.0)) * plot_h

    title_font, label_font, small_font = _font(34), _font(20), _font(17)
    mark = _brand_mark(_MARK_H)
    name = _safe_label(run.name or run_id)
    TRAIN, VAL = (94, 174, 255), (255, 176, 59)

    images: list[Any] = []
    for cutoff in [e for e, _ in val_pts]:
        img = Image.new("RGB", (width, height), _BG)
        d = ImageDraw.Draw(img)

        for i in range(5):
            y = _PAD_T + i * plot_h / 4
            d.line([(_PAD_L, y), (width - _PAD_R, y)], fill=_GRID, width=1)
            d.text(
                (_PAD_L - 14, y - 10),
                f"{hi - i * (hi - lo) / 4:.3f}",
                font=small_font,
                fill=_MUTED,
                anchor="ra",
            )

        d.text((_PAD_L, 42), name, font=title_font, fill=_INK)
        d.text((_PAD_L, 86), f"{train_key} vs {val_key}", font=label_font, fill=_MUTED)
        d.text(
            (width - _PAD_R, 86),
            f"epoch {int(cutoff)} of {int(x1)}",
            font=label_font,
            fill=_MUTED,
            anchor="ra",
        )

        # The best-validation marker appears only once the animation reaches it,
        # so it reads as a discovery rather than a spoiler on frame one.
        if cutoff >= best_epoch:
            bx = px(best_epoch)
            d.line([(bx, _PAD_T), (bx, height - _PAD_B)], fill=(124, 109, 255), width=2)
            d.text((bx + 8, _PAD_T + 6), f"best {val_key}", font=small_font, fill=(124, 109, 255))
            d.ellipse([bx - 6, py(best_val) - 6, bx + 6, py(best_val) + 6], fill=(124, 109, 255))

        for pts, colour in ((train_pts, TRAIN), (val_pts, VAL)):
            drawn = [(e, v) for e, v in pts if e <= cutoff]
            if len(drawn) >= 2:
                d.line([(px(e), py(v)) for e, v in drawn], fill=colour, width=4, joint="curve")

        legend_top = 118
        d.rectangle(
            [width - _PAD_R - 230, legend_top, width - _PAD_R + 6, legend_top + 2 * 26 + 8],
            fill=_BG,
            outline=_GRID,
        )
        for i, (key, colour, pts) in enumerate(
            ((train_key, TRAIN, train_pts), (val_key, VAL, val_pts))
        ):
            ly = legend_top + 14 + i * 26
            d.line([(width - _PAD_R - 220, ly), (width - _PAD_R - 196, ly)], fill=colour, width=4)
            seen = [v for e, v in pts if e <= cutoff]
            value = f"{seen[-1]:.4f}" if seen else "—"
            d.text((width - _PAD_R - 188, ly - 9), key, font=small_font, fill=_INK)
            d.text((width - _PAD_R, ly - 9), value, font=small_font, fill=_MUTED, anchor="ra")

        d.line([(_PAD_L, height - _PAD_B), (width - _PAD_R, height - _PAD_B)], fill=_GRID, width=2)
        wm_y = height - 40
        d.text((width - _PAD_R, wm_y), "epochix.dev", font=small_font, fill=_MUTED, anchor="ra")
        if mark is not None:
            tw = d.textlength("epochix.dev", font=small_font)
            img.paste(mark, (int(width - _PAD_R - tw - mark.width - 8), wm_y - 3), mark)

        images.append(img)

    images.extend([images[-1]] * _HOLD_FRAMES)
    buf = io.BytesIO()
    images[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=int(1000 / max(fps, 1)),
        loop=0,
        optimize=True,
    )
    return buf.getvalue()
