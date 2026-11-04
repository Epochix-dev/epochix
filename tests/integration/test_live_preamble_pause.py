"""A live run that pauses after its preamble is still read in its own format.

When the stream goes quiet before the sniff window fills, the pipeline chooses
a parser on what it has, so a short run is told while it runs. CatBoost prints
"Learning rate set to 0.108196" and then trains; when its first round took
longer than that wait, the parser was chosen on the one line — the universal
parser, for good. All 30 rounds were told without their iteration, under the
name "test", and the record kept the placeholder parser `unknown`. CI found it
on a Windows runner that stalled for 20 ms after the first line.

0.7.40 waited for a line some parser read a number from, and setup lines have
numbers: a pause after Lightning's "IPU available: False, using: 0 IPU cores"
or Ultralytics' "Fast image access (ping: 0.1 ms …" chose the universal parser,
and the story gained frames without an epoch, named `using` or `ping`. A pause
on YOLO's first epoch did too: its parser reads the row, but its sniff had not
seen enough rows to be chosen.

The ingesters here behave like `tail -F`: they never return, so nothing can
come from the end-of-stream code.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

import epochix.parsers.registry as registry
import epochix.pipeline as pipeline
from epochix.models import RawLogLine, RawMetric
from epochix.normalizer.canonical_keys import canonicalize_key, is_recognised
from epochix.parsers.base import BaseParser, ParserContext
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

LOGS = Path(__file__).resolve().parents[1] / "fixtures" / "logs"
DEMO = Path(__file__).resolve().parents[2] / "demo"
IDLE = 0.02


class _PausingIngester:
    """Yields `rows`, waits well past the idle sniff after the first
    `pause_after` of them (never, for None), and never ends."""

    def __init__(self, rows: list[str], pause_after: int | None) -> None:
        self.rows = rows
        self.pause_after = pause_after
        self.yielded = 0

    async def lines(self) -> AsyncIterator[RawLogLine]:
        for i, text in enumerate(self.rows, start=1):
            if self.pause_after is not None and i == self.pause_after + 1:
                await asyncio.sleep(IDLE * 10)
            self.yielded = i
            yield RawLogLine(
                seq=i, timestamp=datetime.now(tz=timezone.utc), text=text, source="stdin"
            )
        while True:
            await asyncio.sleep(3600)


async def _live(ing: _PausingIngester, frames_expected: int) -> RunStore:
    store = RunStore(":memory:")
    task = asyncio.ensure_future(
        pipeline.run_pipeline(ingester=ing, run_id="live", store=store, hub=Hub())
    )
    try:
        for _ in range(250):  # up to ~5 s
            await asyncio.sleep(IDLE)
            if ing.yielded == len(ing.rows) and (
                len(store.get_story_frames("live")) >= frames_expected
            ):
                break
        assert not task.done(), "the stream ended, so this proves nothing"
        return store
    finally:
        task.cancel()


def _spy_on_would_tell(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str, bool]]:
    """Record every idle question: (lines buffered, parser it would choose, answer)."""
    asked: list[tuple[int, str, bool]] = []
    would_tell = pipeline._would_tell

    def _spy(candidate: BaseParser, lines: list[str]) -> bool:
        answer = would_tell(candidate, lines)
        asked.append((len(lines), candidate.name, answer))
        return answer

    monkeypatch.setattr(pipeline, "_would_tell", _spy)
    return asked


@pytest.mark.parametrize(
    ("log", "frames", "epochs", "metric", "parser"),
    [
        ("catboost_real_flat_auc.log", 30, [float(r) for r in range(30)], "val_metric", "boosting"),
        (
            "keras_real_verbose2.log",
            20,
            [float(e) for e in range(1, 21)],
            "val_accuracy",
            "keras_tensorflow",
        ),
    ],
)
async def test_a_pause_after_the_first_line_does_not_choose_the_parser(
    log: str,
    frames: int,
    epochs: list[float],
    metric: str,
    parser: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline, "IDLE_SNIFF_SECS", IDLE)
    asked = _spy_on_would_tell(monkeypatch)
    rows = (LOGS / log).read_bytes().decode("utf-8").split("\n")
    store = await _live(_PausingIngester(rows, pause_after=1), frames)

    # The pause was seen, on the one line the parser would have been chosen on.
    assert (1, "universal", False) in asked, asked
    told = store.get_story_frames("live")
    assert [f.epoch for f in told] == epochs
    assert {f.primary_metric for f in told} == {metric}
    run = store.get_run("live")
    assert run is not None and run.finished_at is None
    assert (run.parser_used, run.primary_metric) == (parser, metric)


def _story(store: RunStore) -> list[tuple[float | None, str | None, float, str]]:
    return [
        (f.epoch, f.primary_metric, f.primary_metric_value, f.grade.value)
        for f in store.get_story_frames("live")
    ]


@pytest.mark.parametrize(
    ("path", "pause_after", "parser"),
    [
        # "IPU available: False, using: 0 IPU cores"
        (DEMO / "pytorch_lightning.log", 3, "pytorch_lightning"),
        # "val: Fast image access (ping: 0.1 ms, read: …, size: …)"
        (LOGS / "yolo_real_ultralytics.log", 35, "ultralytics_yolo"),
        # The first epoch's validation row: the YOLO parser reads the epoch,
        # but YOLO's sniff has not seen enough rows to be chosen.
        (LOGS / "yolo_real_ultralytics.log", 49, "ultralytics_yolo"),
    ],
    ids=["lightning-setup", "yolo-setup", "yolo-first-epoch"],
)
async def test_a_pause_in_a_framework_preamble_tells_the_same_story(
    path: Path, pause_after: int, parser: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "IDLE_SNIFF_SECS", IDLE)
    rows = path.read_bytes().decode("utf-8").split("\n")
    unpaused = _story(await _live(_PausingIngester(rows, pause_after=None), 1))
    assert unpaused and all(epoch is not None for epoch, *_ in unpaused)

    asked = _spy_on_would_tell(monkeypatch)
    store = await _live(_PausingIngester(rows, pause_after=pause_after), len(unpaused))

    # The pause reached the rule, which held the universal parser back there.
    assert (pause_after, "universal", False) in asked, asked
    assert _story(store) == unpaused
    run = store.get_run("live")
    assert run is not None and run.parser_used == parser


async def test_a_loop_with_its_own_metric_names_is_told_on_the_first_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The universal parser needs a name it knows *or* a reading tied to an
    epoch: a hand-written loop's own names are a result when they come with
    their epoch."""
    monkeypatch.setattr(pipeline, "IDLE_SNIFF_SECS", IDLE)
    rows = [f"epoch={e} widget_score={0.5 + e / 10:.2f}" for e in range(1, 5)]
    assert not is_recognised(canonicalize_key("widget_score")), "pick a name we do not know"

    store = await _live(_PausingIngester(rows, pause_after=len(rows)), 4)

    told = store.get_story_frames("live")
    assert [f.epoch for f in told] == [1.0, 2.0, 3.0, 4.0]
    run = store.get_run("live")
    assert run is not None and run.parser_used == "universal"


class _HashParser:
    """A third-party format no built-in parser reads: `## <round> <score>`."""

    name = "hash_plugin"
    priority = 1000

    def sniff(self, sample_lines: list[str]) -> float:
        return 1.0 if any(line.startswith("## ") for line in sample_lines) else 0.0

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        if not line.startswith("## "):
            return []
        _, round_, score = line.split()
        ctx.current_epoch = float(round_)
        return [
            RawMetric(
                seq=ctx.seq,
                epoch=ctx.current_epoch,
                key="val_accuracy",
                value=float(score),
                parser_name=self.name,
                confidence=1.0,
            )
        ]


async def test_a_plugin_format_is_still_told_on_the_first_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No built-in parser reads a plugin's lines, so waiting for one to would
    hold a plugin's live run blank until 200 lines. Its own sniff is trusted."""
    monkeypatch.setattr(pipeline, "IDLE_SNIFF_SECS", IDLE)
    monkeypatch.setattr(registry, "_registry", [_HashParser(), *registry.get_registry()])
    rows = ["## 1 0.50", "## 2 0.60", "## 3 0.70", "## 4 0.75"]
    assert not any(
        pipeline._would_tell(p, rows) for p in registry.get_registry() if pipeline._is_builtin(p)
    ), "a built-in parser now reads this format"

    store = await _live(_PausingIngester(rows, pause_after=len(rows)), 4)

    told = store.get_story_frames("live")
    assert [f.epoch for f in told] == [1.0, 2.0, 3.0, 4.0]
    run = store.get_run("live")
    assert run is not None and run.parser_used == "hash_plugin"
