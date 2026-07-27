"""Regressions found by a cold-start usability test (an outside agent, fresh PC).

Three of its findings were correctness bugs where the dashboard displayed
something untrue:

1. "VAL ACCURACY 123.6%" at epoch 1 — impossible, and reproducible.
2. A "custom" metric series charted next to real accuracy, whose values were
   scraped out of `print(model)` text and tqdm download bars.
3. "Final refinements bring the model to peak form" at epoch 10, on a run that
   peaked at epoch 7 and was overfitting after it — contradicting the tool's own
   diagnostics panel on the same page.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from epochix import parse
from epochix.parsers.base import ParserContext
from epochix.parsers.universal import UniversalParser
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path


def _frames(tmp_path: Path, lines: list[str], locale: str = "en"):  # noqa: ANN202
    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name="t", locale=locale)
    return run, RunStore(db_path=db).get_story_frames(run.id)


# ── 1. the impossible percentage ─────────────────────────────────────────────


def test_every_frame_names_the_metric_it_measured(tmp_path: Path) -> None:
    """Loss on line 1, val_acc only on line 2 — the shape that produced 123.6%.

    An early frame can legitimately predate task detection and measure a loss.
    The bug was that it did not SAY so: the dashboard formatted every frame with
    the run's final primary metric, so a train_loss of 1.2364 was rendered as
    "123.6%" accuracy. Each frame now carries the key it was built from, and a
    value must be plausible for THAT key.
    """
    lines = ["device=cpu batch_size=64 lr=0.001"]
    rows = [
        (1.2364, 0.6234, 0.7710),
        (0.6821, 0.4901, 0.8230),
        (0.5102, 0.4302, 0.8451),
        (0.4413, 0.3901, 0.8590),
        (0.3902, 0.3715, 0.8650),
    ]
    for i, (tl, vl, va) in enumerate(rows, 1):
        lines.append(f"Epoch {i}/5 train_loss={tl:.4f}")
        lines.append(f"  val_loss={vl:.4f} val_acc={va:.4f}")

    run, frames = _frames(tmp_path, lines)
    assert run.primary_metric == "val_accuracy"
    assert frames, "no frames"
    for f in frames:
        assert f.primary_metric is not None, f"epoch {f.epoch}: frame does not name its metric"
        v = f.primary_metric_value
        assert v is not None
        if "acc" in f.primary_metric:
            assert 0.0 <= v <= 1.0, (
                f"epoch {f.epoch}: {v} is not an accuracy - renders as {v * 100:.1f}%"
            )


def test_a_loss_frame_is_never_labelled_with_the_accuracy_key(tmp_path: Path) -> None:
    """The exact 123.6% mechanism: value from one metric, label from another."""
    lines = ["device=cpu"]
    lines.append("Epoch 1/4 train_loss=1.2364")
    lines.append("  val_loss=0.6234 val_acc=0.7710")
    for i, (tl, va) in enumerate([(0.68, 0.823), (0.51, 0.845), (0.44, 0.859)], 2):
        lines.append(f"Epoch {i}/4 train_loss={tl:.4f} val_loss=0.4 val_acc={va:.4f}")

    _, frames = _frames(tmp_path, lines)
    for f in frames:
        if f.primary_metric_value > 1.0:
            assert "acc" not in (f.primary_metric or ""), (
                f"epoch {f.epoch}: {f.primary_metric}={f.primary_metric_value} is impossible"
            )


def test_a_short_loss_only_run_still_tells_its_story(tmp_path: Path) -> None:
    """Guard for the 0.5.2 lesson: waiting for the task must not drop frames."""
    lines = [
        f"Epoch {e}/3 train_loss={0.5 - e * 0.05:.4f} val_loss={0.45 - e * 0.04:.4f}"
        for e in range(1, 4)
    ]
    _, frames = _frames(tmp_path, lines)
    assert len(frames) == 3, f"expected one frame per epoch, got {len(frames)}"


# ── 2. fabricated "custom" metrics ───────────────────────────────────────────


def test_print_model_output_is_not_charted_as_metrics() -> None:
    """Following our own `epochix check` advice must not corrupt the data."""
    parser = UniversalParser()
    ctx = ParserContext(run_id="t")
    for line in (
        "  (2): MaxPool2d(kernel_size=2, stride=2, padding=0, dilation=1, ceil_mode=False)",
        "  (0): Linear(in_features=1568, out_features=128, bias=True)",
        "  (1): Conv2d(1, 32, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1))",
    ):
        assert parser.parse_line(line, ctx) == [], f"scraped a metric out of: {line!r}"


def test_progress_bars_are_not_charted_as_metrics() -> None:
    parser = UniversalParser()
    ctx = ParserContext(run_id="t")
    for line in (
        "Downloading: 100%|##########| 26.4M/26.4M [00:03<00:00, 7.51MB/s]",
        " 45%|####      | 12/26 [00:01<00:01, 9.80it/s]",
    ):
        assert parser.parse_line(line, ctx) == [], f"scraped a metric out of: {line!r}"


def test_run_config_is_not_charted_as_a_metric() -> None:
    """batch_size=64 became a flat "custom" series beside real accuracy."""
    parser = UniversalParser()
    ctx = ParserContext(run_id="t")
    out = parser.parse_line("device=cpu batch_size=64 num_workers=4 lr=0.001", ctx)
    keys = {m.key for m in out}
    assert "batch_size" not in keys and "num_workers" not in keys, keys
    assert "lr" in keys, "the learning-rate schedule is a real metric"


def test_real_metric_lines_still_parse() -> None:
    """The noise filters must not eat genuine metrics."""
    parser = UniversalParser()
    ctx = ParserContext(run_id="t")
    out = parser.parse_line("Epoch 3/10 train_loss=0.4413 val_acc=0.8590", ctx)
    assert {m.key for m in out} == {"train_loss", "val_acc"}


# ── 3. "peak form" while past peak ───────────────────────────────────────────

_PEAK_CLAIMS = re.compile(r"peak form|final refinements|ready for deployment", re.IGNORECASE)


def _overfitting_run() -> list[str]:
    # Peaks at epoch 5 (86.5%), then declines while val_loss rises.
    rows = [
        (0.62, 0.55, 0.771),
        (0.48, 0.47, 0.823),
        (0.41, 0.43, 0.845),
        (0.37, 0.40, 0.859),
        (0.33, 0.3715, 0.865),
        (0.30, 0.381, 0.8612),
        (0.27, 0.4330, 0.852),
        (0.25, 0.45, 0.851),
        (0.23, 0.47, 0.850),
        (0.21, 0.49, 0.852),
    ]
    return [
        f"Epoch {i}/10 train_loss={tl:.4f} val_loss={vl:.4f} val_acc={va:.4f}"
        for i, (tl, vl, va) in enumerate(rows, 1)
    ]


def test_past_peak_run_is_not_called_peak_form(tmp_path: Path) -> None:
    _, frames = _frames(tmp_path, _overfitting_run())
    last = frames[-1].narrative
    assert not _PEAK_CLAIMS.search(last), f"claimed peak form while past peak: {last!r}"
    assert (
        "slipped" in last.lower()
        or "past its best" in last.lower()
        or "passed its peak" in last.lower()
    ), last


def test_past_peak_narrative_names_the_better_epoch(tmp_path: Path) -> None:
    """It should point at the checkpoint that was actually best."""
    _, frames = _frames(tmp_path, _overfitting_run())
    assert "0.8650" in frames[-1].narrative, frames[-1].narrative


def test_a_still_improving_run_keeps_its_positive_story(tmp_path: Path) -> None:
    rows = [
        (0.62, 0.55, 0.62),
        (0.48, 0.47, 0.71),
        (0.41, 0.43, 0.78),
        (0.37, 0.40, 0.83),
        (0.33, 0.37, 0.86),
        (0.30, 0.35, 0.88),
        (0.27, 0.33, 0.90),
    ]
    lines = [
        f"Epoch {i}/7 train_loss={tl:.4f} val_loss={vl:.4f} val_acc={va:.4f}"
        for i, (tl, vl, va) in enumerate(rows, 1)
    ]
    _, frames = _frames(tmp_path, lines)
    last = frames[-1].narrative.lower()
    assert "slipped" not in last and "past its best" not in last, last


def test_past_peak_message_is_localised(tmp_path: Path) -> None:
    _, frames = _frames(tmp_path, _overfitting_run(), locale="fa")
    assert re.search(r"[؀-ۿ]", frames[-1].narrative), frames[-1].narrative


def test_every_past_peak_variant_says_it_and_names_the_best() -> None:
    """Same lesson as the stalled templates: one weak variant = a random third
    of users get a story that still sounds like progress.
    """
    from epochix.story_engine.narrator import _load_special

    for variant in _load_special("_pastpeak", "en", ""):
        low = variant.lower()
        assert not _PEAK_CLAIMS.search(low), f"past-peak variant praises the run: {variant!r}"
        assert "{best}" in variant and "{best_epoch}" in variant, (
            f"past-peak variant does not point at the better checkpoint: {variant!r}"
        )
