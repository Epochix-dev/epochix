"""pytest's output is not a training run, and no story is told from it.

A recorded `pytest -v` of four tests named after metrics, one failing on
`val_loss = 0.42` (tests/fixtures/terminal/pytest.log, recorded by
ordinary_commands_source.py beside it), was told as a run with one reading of
`val_loss`: pytest prints a failing test's source in its report, and the
universal parser read the assignment. In the VS Code extension the terminal
detector also scored the test names and opened the dashboard on it. The
report is now claimed whole, from the rule that opens it ("===== FAILURES
=====", or ERRORS) to the next rule.

The parser lines here start from an empty context, so the extension replays
them (parsers.golden.json) and its port is held to the same answers.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from epochix.ingester.file_batch import FileBatchIngester
from epochix.parsers.base import LINE_CLAIMED, ParserContext
from epochix.parsers.universal import UniversalParser
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

PYTEST_LOG = Path(__file__).resolve().parents[1] / "fixtures" / "terminal" / "pytest.log"


def _read(
    parser: UniversalParser, line: str, ctx: ParserContext
) -> tuple[list[tuple[str, float]], bool]:
    """What the parser read from one line, and whether it claimed the line."""
    ctx.extra.pop(LINE_CLAIMED, None)
    out = parser.parse_line(line, ctx)
    return [(m.key, m.value) for m in out], bool(ctx.extra.get(LINE_CLAIMED))


def _lines() -> list[str]:
    text = PYTEST_LOG.read_text(encoding="utf-8")
    assert "        val_loss = 0.42" in text, "the recording no longer shows the premise"
    return text.splitlines()


def test_the_recorded_pytest_run_tells_nothing() -> None:
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(
            ingester=FileBatchIngester("p", str(PYTEST_LOG)), run_id="p", store=store, hub=Hub()
        )
    )
    assert store.get_metric_events("p") == []
    assert store.get_story_frames("p") == []


def test_the_failure_report_is_claimed_and_the_next_section_is_read() -> None:
    lines = _lines()
    opens = lines.index(next(ln for ln in lines if ln.startswith("=") and " FAILURES " in ln))
    closes = lines.index(next(ln for ln in lines if " short test summary info " in ln))
    assert opens < closes
    ctx = ParserContext(run_id="t")
    parser = UniversalParser()
    for line in lines[:opens]:
        assert _read(parser, line, ctx) == ([], False), line
    for line in lines[opens:closes]:
        assert _read(parser, line, ctx) == ([], True), line
    # The report is over at the next rule: what follows is read as before.
    assert _read(parser, lines[closes], ctx) == ([], False)
    assert _read(parser, "accuracy = 0.9375", ctx) == ([("accuracy", 0.9375)], False)


@pytest.mark.parametrize("section", ["FAILURES", "ERRORS"])
def test_either_report_is_claimed(section: str) -> None:
    ctx = ParserContext(run_id="t")
    parser = UniversalParser()
    assert _read(parser, f"{'=' * 20} {section} {'=' * 20}", ctx) == ([], True)
    assert _read(parser, "    loss = 0.31", ctx) == ([], True)
    assert _read(parser, "E       assert 0.31 < 0.3", ctx) == ([], True)


def test_a_rule_that_opens_no_report_claims_nothing() -> None:
    ctx = ParserContext(run_id="t")
    parser = UniversalParser()
    assert _read(parser, "=" * 10 + " warnings summary " + "=" * 10, ctx) == ([], False)
    assert _read(parser, "Epoch 3/10 val_accuracy=0.81", ctx) == ([("val_accuracy", 0.81)], False)
    # A line of equals signs with no title is not one of pytest's rules.
    assert _read(parser, "=" * 40, ctx) == ([], False)
    assert _read(parser, "loss = 0.5", ctx) == ([("loss", 0.5)], False)
