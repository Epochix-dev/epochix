"""Every corpus log, fed straight to the parser the pipeline chooses for it.

The pipeline offers a line its parser could not read to the other parsers, so
a run's story can be right while its own parser reads little of it. This pins
what each parser reads alone: the last value of the story's metric, as the
corpus truth states it — or, for the logs whose story the fallbacks tell, that
it reads none.

It is also where the extension's parsers meet every real line: the calls made
here are recorded (scripts/parser_recorder.py) into parsers.golden.json, which
the extension replays through its TypeScript ports line by line.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from epochix.ingester.file_batch import FileBatchIngester
from epochix.normalizer.canonical_keys import canonicalize_key
from epochix.parsers.base import LINE_CLAIMED, ParserContext
from epochix.parsers.registry import get_registry
from epochix.pipeline import _clean_line, run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

ROOT = Path(__file__).resolve().parents[2]
TRUTH: dict[str, dict[str, Any]] = json.loads(
    (ROOT / "tests" / "fixtures" / "corpus_truth.json").read_text(encoding="utf-8")
)
TOLD = sorted(name for name, t in TRUTH.items() if t["metric"])

# The story's metric is on lines the chosen parser does not read at all:
# fingerprint_matching.log's `train_loss=... EER=...` lines sit under Keras
# "Epoch 15/50" headers, and mixed_frameworks.log's under a Keras header too.
TOLD_BY_THE_FALLBACKS = {"fingerprint_matching.log", "mixed_frameworks.log"}


def _lines(path: Path) -> list[str]:
    """The log's lines as the ingester reads them: split on newlines only.

    read_text() translates a lone carriage return into a line break, so every
    redraw of a progress bar came out as a line of its own — a feed the
    pipeline never gives a parser, where _clean_line keeps a line's last draw.
    """
    return path.read_bytes().decode("utf-8").split("\n")


def _chosen_parser(path: Path) -> str:
    store = RunStore(":memory:")
    run = asyncio.run(
        run_pipeline(ingester=FileBatchIngester("p", str(path)), run_id="p", store=store, hub=Hub())
    )
    return run.parser_used


def test_every_log_with_a_story_is_here() -> None:
    assert len(TOLD) >= 40, "the corpus went missing"
    assert TOLD_BY_THE_FALLBACKS.issubset(TOLD)


@pytest.mark.parametrize("name", TOLD)
def test_the_chosen_parser_reads_the_log_alone(name: str) -> None:
    truth = TRUTH[name]
    path = ROOT / truth["path"]
    chosen = _chosen_parser(path)
    parser = next(p for p in get_registry() if p.name == chosen)

    ctx = ParserContext(run_id="p")
    read = []
    for raw in _lines(path):
        ctx.seq += 1
        read += parser.parse_line(_clean_line(raw), ctx)
        ctx.extra.pop(LINE_CLAIMED, None)
    flush = getattr(parser, "flush", None)
    if flush is not None:
        read += flush(ctx)

    story = [m.value for m in read if truth["metric"] in (m.key, canonicalize_key(m.key))]
    if name in TOLD_BY_THE_FALLBACKS:
        assert story == [], f"{chosen} now reads {truth['metric']}: update this test"
    else:
        assert story, f"{chosen} read no {truth['metric']}"
        assert round(story[-1], 4) == truth["last_value"]


def test_the_accelerate_parser_reads_its_own_recording() -> None:
    """accelerate_real.log is Accelerate's own output, and the Hugging Face
    parser is chosen for it — so without this the Accelerate parser would meet
    no real line here, and its port in the extension none in the replay."""
    path = ROOT / TRUTH["accelerate_real.log"]["path"]
    lines = _lines(path)
    parser = next(p for p in get_registry() if p.name == "accelerate")
    assert parser.sniff(lines) > 0
    ctx = ParserContext(run_id="a")
    read = [m for line in lines for m in parser.parse_line(_clean_line(line), ctx)]
    accuracy = [(m.epoch, m.step, m.value) for m in read if m.key == "val_accuracy"]
    assert accuracy == [(0.0, 10, 0.845), (1.0, 20, 0.855), (2.0, 30, 0.855), (3.0, 40, 0.86)]
