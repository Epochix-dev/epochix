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


def _font(size: int) -> Any:  # noqa: ANN401 - PIL font object, optional dep
    from PIL import ImageFont

    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_gif(
    run_id: str,
    store: RunStore,
    *,
    fps: int = _FPS,
    width: int = _W,
    height: int = _H,
) -> bytes:
    """Render the run's primary-metric curve as an animated GIF."""
    Image, ImageDraw = _require_pillow()

    # Clamp before allocating anything.
    width = max(_MIN_DIM, min(int(width), _MAX_DIM))
    height = max(_MIN_DIM, min(int(height), _MAX_DIM))
    fps = max(1, min(int(fps), _MAX_FPS))

    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id!r}")

    frames = store.get_story_frames(run_id)
    # One metric only: an early frame can predate task detection and measure
    # something else, and joining a loss to an accuracy would be a false curve.
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
    if len(points) < 2:
        raise ValueError("This run has too few epochs to animate.")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or (abs(hi) or 1.0)
    lo -= span * 0.12
    hi += span * 0.12
    # Padding must not push the axis past what the metric can be. An accuracy
    # axis topped at 1.007 shows a value no model can reach — the same class of
    # impossible number as the 123.6% this project shipped once already.
    if _is_bounded_unit(metric):
        lo, hi = max(lo, 0.0), min(hi, 1.0)
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
        # that turns a viewer into a visitor.
        d.text(
            (width - _PAD_R, height - 40), "epochix.dev", font=small_font, fill=_MUTED, anchor="ra"
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
