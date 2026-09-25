"""Every log in the repository, through the real pipeline, against what it contains.

Two fixtures here (ansi_colors.log, mixed_frameworks.log) were never read by
any test, and both came out wrong. Driving the whole corpus found more:

* garbage.log — a web server's log — got a training story: "Response sent: 200"
  and "keys: 0.234" were filed under one name, "custom", and narrated as a
  model "past its best, 200.0 -> 0.234", graded F.
* fingerprint_matching.log, a headline demo, told 50 epochs as ONE reading: the
  Keras parser won detection on its "Epoch 15/50" lines and could not read the
  `train_loss=... EER=...` lines under them. It also charted the dataset sizes
  ("Train: 4200 | Val: 800").
* Every Keras / Lightning run's first frame was TRAINING accuracy and the rest
  validation accuracy — one chart, two series, and the baseline from the wrong
  one; a one-epoch run was graded on training accuracy.
* A tqdm "[00:12<00:00" became a metric named `00`; an orphaned colour code a
  metric named `1mloss`.

The expectations were reviewed against the files, not copied from a run: the
frame count is the number of epochs that print the story's metric, the value is
the last one the log prints, and the key set is exactly the metrics it reports.
A log added to demo/ or tests/fixtures/logs without an entry here fails.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

ROOT = Path(__file__).resolve().parents[2]
LOGS = {
    **{p.name: p for p in (ROOT / "demo").glob("*.log")},
    **{p.name: p for p in (ROOT / "tests" / "fixtures" / "logs").glob("*.log")},
    "vscode-demo.log": ROOT / "epochix-vscode" / "media" / "demo.log",
}

# Reviewed expectations, shared with the VS Code extension's engine test
# (epochix-vscode/src/test/suite/corpusParity.test.ts): one truth, two engines.
TRUTH_FILE = ROOT / "tests" / "fixtures" / "corpus_truth.json"
TRUTH: dict[str, dict[str, Any]] = json.loads(TRUTH_FILE.read_text(encoding="utf-8"))


def test_every_log_has_an_expectation() -> None:
    assert len(LOGS) >= 38, "the corpus went missing"
    assert set(LOGS) == set(TRUTH)


def _run(
    path: Path,
) -> tuple[str, str | None, int, float | None, tuple[str, ...], float | None, str | None]:
    store = RunStore(":memory:")
    run = asyncio.run(
        run_pipeline(ingester=FileBatchIngester("c", str(path)), run_id="c", store=store, hub=Hub())
    )
    frames = store.get_story_frames("c")
    events = store.get_metric_events("c")
    last = frames[-1] if frames else None
    # The epoch the story's metric first appears at: a run whose first epochs
    # were told on a different series shows up here, not in the frame count.
    starts = [f.epoch for f in frames if last and f.primary_metric == last.primary_metric]
    return (
        run.task_type.value if run.task_type else "custom",
        last.primary_metric if last else None,
        len(frames),
        round(last.primary_metric_value, 4) if last else None,
        tuple(sorted({e.canonical_key for e in events})),
        min((e for e in starts if e is not None), default=None),
        # Why the final letter deserves less weight, if it does. Derived, but
        # both engines must reach it from the same log.
        last.grade_note if last else None,
    )


@pytest.mark.parametrize("name", sorted(TRUTH))
def test_the_log_tells_what_it_contains(name: str) -> None:
    task, metric, frames, last_value, keys, from_epoch, grade_note = _run(LOGS[name])
    want = TRUTH[name]
    assert (ROOT / want["path"]).resolve() == LOGS[name].resolve()
    assert keys == tuple(want["keys"]), f"metrics stored: {keys}"
    assert (task, metric) == (want["task"], want["metric"])
    assert frames == want["frames"]
    assert last_value == want["last_value"]
    assert from_epoch == want["metric_from_epoch"]
    assert grade_note == want["grade_note"]


def test_one_story_metric_per_run() -> None:
    """The first frame is not a different series from the rest."""
    for name in ("pytorch_lightning_30ep.log", "keras_short.log", "pl_high_accuracy.log"):
        store = RunStore(":memory:")
        asyncio.run(
            run_pipeline(
                ingester=FileBatchIngester("s", str(LOGS[name])), run_id="s", store=store, hub=Hub()
            )
        )
        assert {f.primary_metric for f in store.get_story_frames("s")} == {"val_accuracy"}, name
