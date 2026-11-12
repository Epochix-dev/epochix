"""Loops that count steps, and scripts that print "name value" with no delimiter.

A probe on 2026-11-10 — lines typed from memory of each layout — said Epochix
read nothing from a LoRA trainer or the PyTorch ImageNet example, and half of
a nanoGPT line. Recording the real runs (tests/fixtures/logs/README.md) showed
the rest:

* **nanoGPT** (`nanogpt_real.log`). `step 250: train loss 2.4293, val loss
  2.4447` was read as ONE training loss — the validation one. The loss printed
  every ten iterations (`iter 260: loss 2.4461, time 16.42ms, …`) was never
  read. And the config file nanoGPT echoes before training gave the run nine
  metrics, `n_layer` and `max_iters` among them.
* **The PyTorch ImageNet example** (`pytorch_imagenet_real.log`). No metric at
  all: `Epoch: [0][ 1/32]<TAB>Loss 7.1568e+00 (7.1568e+00)<TAB>Acc@1 …` has no
  delimiter, and ` *   Acc@1 10.333 Acc@5 64.667` no counter.
* **diffusers' SDXL LoRA script** (`diffusers_lora_real.log`). One tqdm bar for
  the whole run, redrawn in place: the 120-step run is four lines in a file,
  and its story was told on "Process index: 0".

These runs count steps, not epochs, and two of the three print only a loss:
the story is a loss told by step.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path

import pytest

from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import MetricEvent, Run, StoryFrame
from epochix.parsers.base import LINE_CLAIMED, ParserContext
from epochix.parsers.progress_meter import ProgressMeterParser
from epochix.parsers.step_bar import StepBarParser, step_bar_redraws
from epochix.parsers.universal import UniversalParser
from epochix.pipeline import _line_states, run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

LOGS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "logs"
NANOGPT = LOGS / "nanogpt_real.log"
IMAGENET = LOGS / "pytorch_imagenet_real.log"
LORA = LOGS / "diffusers_lora_real.log"


def _told(log: Path) -> tuple[Run, list[StoryFrame], list[MetricEvent]]:
    assert log.stat().st_size > 0
    store = RunStore(":memory:")
    run = asyncio.run(
        run_pipeline(ingester=FileBatchIngester("s", str(log)), run_id="s", store=store, hub=Hub())
    )
    return run, store.get_story_frames("s"), store.get_metric_events("s")


def _read(parser: object, line: str, ctx: ParserContext) -> tuple[list[tuple[str, float]], bool]:
    """What a parser read from one line, and whether it claimed the line."""
    ctx.extra.pop(LINE_CLAIMED, None)
    out = parser.parse_line(line, ctx)  # type: ignore[attr-defined]
    return [(m.key, m.value) for m in out], bool(ctx.extra.get(LINE_CLAIMED))


# ── The recordings are recordings ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("log", "script", "upstream"),
    [
        (NANOGPT, "nanogpt_real_source.py", "train.py"),
        (IMAGENET, "pytorch_imagenet_real_source.py", "main.py"),
        (LORA, "diffusers_lora_real_source.py", "train_dreambooth_lora_sdxl.py"),
    ],
    ids=["nanogpt", "imagenet", "lora"],
)
def test_each_recording_ships_with_the_script_that_ran_it(
    log: Path, script: str, upstream: str
) -> None:
    assert log.stat().st_size > 2000
    source = (LOGS / script).read_text(encoding="utf-8")
    # The trainer is the library's own script, run as shipped — not a loop
    # written here in its shape.
    assert upstream in source and "subprocess.run" in source


# ── nanoGPT ──────────────────────────────────────────────────────────────────


def test_nanogpt_is_told_by_its_validation_loss_step_by_step() -> None:
    run, frames, events = _told(NANOGPT)
    assert run.parser_used == "universal"
    assert run.primary_metric == "val_loss"
    assert {f.primary_metric for f in frames} == {"val_loss"}
    # One reading per `step N:` line, at the step it names.
    assert [f.epoch for f in frames] == [float(n) for n in range(0, 2001, 250)]
    assert [f.primary_metric_value for f in frames][:2] == [4.1649, 2.4447]
    assert frames[-1].primary_metric_value == 1.8857
    assert frames[-1].grade_basis == "improvement"

    counts = Counter(e.canonical_key for e in events)
    # Nine estimates on the `step` lines and the loss of every tenth iteration.
    assert counts == {"val_loss": 9, "train_loss": 9 + 201}


def test_nanogpt_s_two_losses_are_not_one_series() -> None:
    """`train loss 2.4293, val loss 2.4447`: the second is not a training loss."""
    _run, _frames, events = _told(NANOGPT)
    at_250 = {(e.raw_key, e.canonical_key, e.value) for e in events if e.step == 250}
    assert at_250 == {
        ("train_loss", "train_loss", 2.4293),
        ("val_loss", "val_loss", 2.4447),
        ("loss", "train_loss", 2.4904),
    }
    # Every reading carries the step its own line names.
    assert all(e.epoch == float(e.step) for e in events if e.step is not None)
    assert {e.step for e in events} == set(range(0, 2001, 10))


def test_nanogpt_s_config_echo_is_not_a_metric() -> None:
    text = NANOGPT.read_text(encoding="utf-8")
    assert "n_layer = 6" in text and "Overriding: n_layer = 4" in text
    assert "learning_rate = 1e-3 #" in text
    _run, _frames, events = _told(NANOGPT)
    assert {e.canonical_key for e in events} == {"train_loss", "val_loss"}


def test_a_pair_may_end_at_a_comma_and_carry_its_split() -> None:
    ctx = ParserContext(run_id="t")
    parser = UniversalParser()
    assert _read(parser, "step 250: train loss 2.4293, val loss 2.4447", ctx) == (
        [("train_loss", 2.4293), ("val_loss", 2.4447)],
        False,
    )
    assert (ctx.current_step, ctx.current_epoch) == (250, 250.0)
    assert _read(parser, "iter 260: loss 2.4461, time 16.42ms, mfu 0.08%", ctx) == (
        [("loss", 2.4461)],
        False,
    )
    assert (ctx.current_step, ctx.current_epoch) == (260, 260.0)


@pytest.mark.parametrize(
    "line",
    [
        # No counter opens the line: a sentence, however much it looks like one.
        "the train loss 2.4293, and the val loss 2.4447",
        "final loss 0.5, accuracy 0.9",
        "Done in 42.1s, loss 0.3",
        # A counter, but names nothing recognises.
        "step 12: wrote 3, skipped 4; kept 9",
        "step 3: batch of 64, 12 workers, took 31.5",
        # A number glued to its unit is not a value.
        "iter 10: time 16.42ms, mfu 0.08%",
        # The verb, not an inception score.
        "step 40: the answer is 0.5, or so",
    ],
)
def test_prose_is_still_not_read(line: str) -> None:
    ctx = ParserContext(run_id="t")
    assert _read(UniversalParser(), line, ctx)[0] == []


def test_a_step_is_the_axis_only_while_no_epoch_is_printed() -> None:
    ctx = ParserContext(run_id="t")
    parser = UniversalParser()
    # Not a reading: the counter does not become the run's position.
    _read(parser, "Step 3: fetching the data", ctx)
    assert ctx.current_epoch is None
    _read(parser, "step 500: train loss 1.9, val loss 2.0", ctx)
    assert ctx.current_epoch == 500.0
    # The run has epochs after all, and a step now counts within one.
    _read(parser, "Epoch 2/10 val_accuracy=0.71", ctx)
    assert ctx.current_epoch == 2.0
    out, _claimed = _read(parser, "step 100: train loss 1.7, val loss 1.8", ctx)
    assert out == [("train_loss", 1.7), ("val_loss", 1.8)]
    assert (ctx.current_epoch, ctx.current_step) == (2.0, 100)


@pytest.mark.parametrize(
    "line",
    [
        "learning_rate = 1e-3 # with baby networks can afford to go a bit higher",
        "eval_interval = 250 # keep frequent because we'll overfit",
        "Overriding: n_layer = 4",
        "Overriding: learning_rate = 0.0003",
        "Overriding config with config/train_shakespeare_char.py:",
    ],
)
def test_a_line_of_settings_is_claimed(line: str) -> None:
    ctx = ParserContext(run_id="t")
    assert _read(UniversalParser(), line, ctx) == ([], True)


def test_an_assignment_without_a_comment_is_still_a_result() -> None:
    ctx = ParserContext(run_id="t")
    assert _read(UniversalParser(), "accuracy = 0.9375", ctx) == ([("accuracy", 0.9375)], False)
    # Nor is a `#` after a pair printed without spaces a line of source.
    assert _read(UniversalParser(), "loss=0.25 # 3", ctx) == ([("loss", 0.25)], False)


# ── The PyTorch ImageNet example ─────────────────────────────────────────────


def test_the_imagenet_example_is_told_by_its_validation_accuracy() -> None:
    run, frames, events = _told(IMAGENET)
    assert run.parser_used == "progress_meter"
    assert run.task_type is not None and run.task_type.value == "classification"
    assert run.primary_metric == "val_accuracy"

    told = [f for f in frames if f.primary_metric == "val_accuracy"]
    # One per ` * Acc@1 …` line, at the number of epochs finished.
    assert [f.epoch for f in told] == [float(n) for n in range(1, 9)]
    assert [round(f.primary_metric_value, 5) for f in told][:3] == [0.10333, 0.13333, 0.27]
    assert told[-1].primary_metric_value == 0.89
    assert told[-1].grade_basis == "thresholds"
    # Before the first validation the run has printed a loss and nothing else.
    before = [f for f in frames if f.primary_metric != "val_accuracy"]
    assert {f.primary_metric for f in before} == {"train_loss"}
    assert all(f.epoch is not None and f.epoch < 1.0 for f in before)
    assert frames.index(told[0]) == len(before)

    counts = Counter(e.canonical_key for e in events)
    assert counts == {"train_loss": 56, "accuracy": 8, "val_accuracy": 8, "top5_accuracy": 8}


def test_the_meters_percentages_are_fractions() -> None:
    """`Acc@1 11.000` is 11%, and `Acc@1 0.39` would be 0.39% — not 39%."""
    _run, _frames, events = _told(IMAGENET)
    accuracies = [e for e in events if e.canonical_key.endswith("accuracy")]
    assert accuracies and all(0.0 <= e.value <= 1.0 for e in accuracies)
    ctx = ParserContext(run_id="t")
    parser = ProgressMeterParser()
    _read(parser, "Epoch: [0][   1/5005]\tLoss 6.9e+00 (6.9e+00)\tAcc@1   0.39 (  0.39)", ctx)
    out, _claimed = _read(parser, " *   Acc@1 0.390 Acc@5 1.953", ctx)
    assert out == [("val_Acc@1", 0.0039), ("val_Acc@5", 0.01953), ("Acc@1", 0.0039)]


def test_a_training_row_gives_its_loss_at_its_place_in_the_epoch() -> None:
    ctx = ParserContext(run_id="t")
    parser = ProgressMeterParser()
    row = (
        "Epoch: [2][16/32]\tTime  0.544 ( 0.560)\tData  0.038 ( 0.050)\t"
        "Loss 2.3462e+00 (3.5980e+00)\tAcc@1  12.50 (  9.77)\tAcc@5  50.00 ( 44.53)"
    )
    assert _read(parser, row, ctx) == ([("Loss", 2.3462)], False)
    assert (ctx.current_epoch, ctx.current_step) == (2.5, 2 * 32 + 16)
    # A validation pass caught part-way through is not its result.
    test_row = (
        "Test: [ 6/10]\tTime  0.183 ( 0.193)\tLoss 3.7912e+00 (4.1547e+00)\tAcc@1   0.00 (  1.56)"
    )
    assert _read(parser, test_row, ctx) == ([], True)
    # The result is, with the training accuracy of the epoch it follows.
    assert _read(parser, " *   Acc@1 11.000 Acc@5 49.667", ctx) == (
        [("val_Acc@1", 0.11), ("val_Acc@5", 0.49667), ("Acc@1", 0.0977)],
        False,
    )
    assert ctx.current_epoch == 3.0
    # Told once: a second result without training rows carries no training accuracy.
    assert _read(parser, " *   Acc@1 12.000 Acc@5 50.000", ctx)[0] == [
        ("val_Acc@1", 0.12),
        ("val_Acc@5", 0.5),
    ]


def test_the_meter_parser_leaves_other_lines_alone() -> None:
    ctx = ParserContext(run_id="t")
    parser = ProgressMeterParser()
    for line in ("=> creating model 'resnet18'", "Epoch 3/10: loss=0.5", " * done", ""):
        assert _read(parser, line, ctx)[0] == []
    assert parser.sniff(["=> creating model 'resnet18'", "Epoch 3/10: loss=0.5"]) == 0.0
    assert parser.sniff(IMAGENET.read_text(encoding="utf-8").split("\n")) == 0.9


# ── A run-long step bar (diffusers' LoRA script) ─────────────────────────────


def test_a_lora_run_is_told_step_by_step() -> None:
    raw = LORA.read_bytes().decode("utf-8")
    # The whole bar is a handful of lines in the file: read in their final
    # state, as every other line is, the run would be this many readings.
    assert sum(1 for line in raw.split("\n") if "Steps:" in line) == 5
    assert raw.count("\rSteps:") > 200

    run, frames, events = _told(LORA)
    assert run.parser_used == "step_bar"
    assert run.primary_metric == "train_loss"
    assert {f.primary_metric for f in frames} == {"train_loss"}
    # One reading per step, at the step the bar stood at, of the 120 it names.
    assert [f.epoch for f in frames] == [float(n) for n in range(1, 121)]
    assert [f.primary_metric_value for f in frames][:3] == [0.00856, 0.0162, 0.025]
    assert frames[-1].primary_metric_value == 0.00357
    assert frames[-1].progress == 1.0
    # A frame's seq is its key in the store: none was dropped for sharing one.
    assert len({f.seq for f in frames}) == 120

    assert Counter(e.canonical_key for e in events) == {"train_loss": 120, "lr": 120}
    assert all(e.step == int(e.epoch or 0) for e in events)


def test_a_redraw_is_a_reading_when_its_values_changed() -> None:
    ctx = ParserContext(run_id="t")
    parser = StepBarParser()
    bar = "Steps:  {pct}%|###3      | {n}/120 [00:26<00:43,  1.85it/s{post}]"
    # Before the first step there is nothing on the bar.
    assert _read(parser, bar.format(pct=0, n=0, post=""), ctx) == ([], True)
    assert _read(parser, bar.format(pct=1, n=1, post=""), ctx) == ([], True)
    assert _read(parser, bar.format(pct=1, n=1, post=", loss=0.00856, lr=0.0001"), ctx) == (
        [("loss", 0.00856), ("lr", 0.0001)],
        False,
    )
    assert (ctx.current_step, ctx.current_epoch, ctx.total_epochs) == (1, 1.0, 120)
    # The counter moved on; the values are still the last step's.
    assert _read(parser, bar.format(pct=2, n=2, post=", loss=0.00856, lr=0.0001"), ctx) == (
        [],
        True,
    )
    assert ctx.current_step == 1
    assert _read(parser, bar.format(pct=2, n=2, post=", loss=0.0162, lr=0.0001"), ctx)[0] == [
        ("loss", 0.0162),
        ("lr", 0.0001),
    ]
    assert ctx.current_step == 2
    # The same line drawn again, with whatever was printed after it.
    again = bar.format(pct=2, n=2, post=", loss=0.0162, lr=0.0001") + "Saving current state"
    assert _read(parser, again, ctx) == ([], True)


def test_only_a_bar_that_counts_steps_is_read_redraw_by_redraw() -> None:
    steps = "\rSteps:   1%|  | 1/120 [00:06<12:07, loss=0.5, lr=0.1]\rSteps:   2%|  | 2/120 [00:07<09:00, loss=0.4, lr=0.1]"
    assert step_bar_redraws(steps) == [
        "Steps:   1%|  | 1/120 [00:06<12:07, loss=0.5, lr=0.1]",
        "Steps:   2%|  | 2/120 [00:07<09:00, loss=0.4, lr=0.1]",
    ]
    assert len(_line_states(steps)) == 2
    # An epoch's bar is read in its final state: the redraws before it are the
    # epoch caught part-way through.
    epoch = "\rEpoch 1/12:  12%|#1  | 5/43 [00:00<00:00, loss=2.3010]\rEpoch 1/12: 100%|####| 43/43 [00:01<00:00, loss=1.2]"
    assert step_bar_redraws(epoch) is None
    assert _line_states(epoch) == ["Epoch 1/12: 100%|####| 43/43 [00:01<00:00, loss=1.2]"]
    assert step_bar_redraws("no carriage return") is None
    assert _line_states("plain line\r") == ["plain line"]


def test_a_bar_line_longer_than_any_line_of_text_keeps_its_last_step() -> None:
    """A real run's bar is hundreds of kilobytes on one line; the cap on a
    line's length is for text, and would cut the later steps off."""
    redraws = [
        f"Steps: {n // 50:3d}%|#####     | {n}/5000 [00:26<00:43,  1.85it/s, loss=0.{n:04d}, lr=0.0001]"
        for n in range(1, 5001)
    ]
    line = "\r" + "\r".join(redraws)
    assert len(line) > 300_000
    states = _line_states(line)
    assert len(states) == 5000 and states[-1] == redraws[-1]


def test_the_step_bar_parser_leaves_other_bars_alone() -> None:
    ctx = ParserContext(run_id="t")
    parser = StepBarParser()
    others = [
        "Loading pipeline components...:  43%|####2     | 3/7 [00:05<00:06,  1.66s/it]",
        "Epoch 1/12:  12%|#1        | 5/43 [00:00<00:00, 49.79it/s, acc=0.1125, loss=2.3010]",
        "Total optimization steps = 120",
    ]
    for line in others:
        assert _read(parser, line, ctx) == ([], False)
    assert parser.sniff(others) == 0.0
