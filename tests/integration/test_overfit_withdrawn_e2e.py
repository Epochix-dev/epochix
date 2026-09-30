"""The real ResNet-18 run, through the whole pipeline: its warm-up blip is withdrawn.

Unit tests replay the numbers; this drives the log the way `epochix run`
does, and checks what a finished run's frames carry to the dashboard.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

LOG = Path(__file__).resolve().parents[1] / "fixtures" / "logs" / "resnet18_cifar10.log"


def test_the_overfit_warning_is_withdrawn_a_frame_later() -> None:
    assert LOG.stat().st_size > 0
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("r", str(LOG)), run_id="r", store=store, hub=Hub())
    )
    frames = store.get_story_frames("r")
    assert len(frames) == 30
    overfit = [
        (f.epoch, w.kind) for f in frames for w in f.warnings if w.kind.startswith("overfit")
    ]
    assert overfit == [(5.0, "overfit"), (6.0, "overfit_cleared")]
