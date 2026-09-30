"""A frame sees its whole log line.

The engine builds a frame when the story's metric arrives and reads every
other metric from history. The pipeline fed it one event at a time, so a
metric printed AFTER the story's metric on the same line reached the next
frame: on the real ResNet-18 log, whose lines end
`val_accuracy=0.9357 lr=0.00442 epoch_time=5.6s`, the learning-rate drop at
epoch 28 reported the epoch 26 -> 27 change, and the last line's drop never
reached any frame.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

LOG = Path(__file__).resolve().parents[1] / "fixtures" / "logs" / "resnet18_cifar10.log"
_LINE = re.compile(r"^Epoch (\d{1,4})/\d{1,4} .{0,200}? lr=([\d.]{1,16}) ")


def _lr_by_epoch() -> dict[int, float]:
    out: dict[int, float] = {}
    for line in LOG.read_text(encoding="utf-8").splitlines():
        m = _LINE.match(line)
        if m:
            out[int(m.group(1))] = float(m.group(2))
    return out


def test_each_lr_drop_is_reported_at_the_epoch_it_happened() -> None:
    lr = _lr_by_epoch()
    assert len(lr) == 30, "the fixture's epoch lines were not all read"

    # What the log says: every epoch whose lr fell below 0.6x the one before.
    expected = [
        (float(e), f"{lr[e - 1]:.2e}", f"{lr[e]:.2e}")
        for e in range(2, 31)
        if lr[e] < lr[e - 1] * 0.6
    ]
    assert expected, "the fixture has no learning-rate drop to test"

    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("r", str(LOG)), run_id="r", store=store, hub=Hub())
    )
    reported = [
        (f.epoch, w.message)
        for f in store.get_story_frames("r")
        for w in f.warnings
        if w.kind == "lr_drop"
    ]
    assert [(epoch, f"from {old} to {new}") for epoch, old, new in expected] == [
        (epoch, re.sub(r"^.*(from \S+ to \S+)\.$", r"\1", text)) for epoch, text in reported
    ]
    # The last line's drop (epoch 30) used to reach no frame at all.
    assert reported[-1][0] == 30.0
