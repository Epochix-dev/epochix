"""pytest plugin: record every parser call a test makes, for the extension to replay.

The parsers exist twice — here and in ``epochix-vscode/src/parsers/`` — and
the extension's copies drifted behind and reintroduced fixed bugs. Its corpus
test (``corpusParity.test.ts``) compares the two only on whole logs, through
the whole engine; the hundreds of lines the Python parser tests feed a parser
directly were never given to the TypeScript one.

Loaded by ``scripts/gen_ts_engine_tables.py`` (``-p parser_recorder``), which
runs the parser tests and writes what it records to ``parsers.golden.json``.
Only calls made from a test file are kept: a parser the pipeline drives in an
integration test is the corpus test's business, and would make the file huge.

Each test's calls are grouped by the context they share. A context that came
to its first call carrying state the extension's context cannot hold — any
``extra`` entry — is left out and counted, not guessed at.
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from epochix.models import RawMetric
from epochix.parsers.accelerate import AccelerateParser
from epochix.parsers.base import LINE_CLAIMED, BaseParser, ParserContext
from epochix.parsers.boosting import BoostingParser
from epochix.parsers.fastai import FastAIParser
from epochix.parsers.huggingface import HFParser
from epochix.parsers.keras_tensorflow import KerasParser
from epochix.parsers.pytorch_lightning import PLParser
from epochix.parsers.ultralytics_yolo import YOLOParser
from epochix.parsers.universal import UniversalParser

# The parsers the extension has a port of (epochix-vscode/src/parsers/).
PORTED = (
    AccelerateParser,
    BoostingParser,
    FastAIParser,
    HFParser,
    KerasParser,
    PLParser,
    UniversalParser,
    YOLOParser,
)

TESTS = Path(__file__).resolve().parents[1] / "tests"

_current: str | None = None
# nodeid -> list of sequences; a sequence is {"start": {...}, "events": [...]}
_tests: dict[str, list[dict[str, Any]]] = {}
# id(ctx) -> (ctx, sequence); the ctx is kept so its id is not reused.
_open: dict[int, tuple[ParserContext, dict[str, Any] | None]] = {}
_skipped = 0


def _num(v: float | str | None) -> float | str | None:
    """JSON has no NaN or infinity; the replay reads these strings back."""
    if v is None or isinstance(v, str) or math.isfinite(v):
        return v
    return "nan" if math.isnan(v) else ("inf" if v > 0 else "-inf")


def _metrics(out: list[RawMetric]) -> list[list[Any]]:
    return [[m.key, _num(m.value), _num(m.epoch), m.step, m.seq] for m in out]


def _state(ctx: ParserContext) -> list[Any]:
    return [_num(ctx.current_epoch), ctx.current_step, ctx.total_epochs]


def _from_a_test() -> bool:
    # Two frames up: the wrapper, then whoever called the parser.
    caller = sys._getframe(2).f_globals.get("__file__") or ""
    return Path(caller).resolve().is_relative_to(TESTS)


def _sequence(ctx: ParserContext) -> dict[str, Any] | None:
    global _skipped
    if id(ctx) in _open and _open[id(ctx)][0] is ctx:
        return _open[id(ctx)][1]
    seq: dict[str, Any] | None = None
    if ctx.extra:
        _skipped += 1
    elif _current is not None:
        seq = {"start": _state(ctx), "events": []}
        _tests.setdefault(_current, []).append(seq)
    _open[id(ctx)] = (ctx, seq)
    return seq


def _wrap_parse(original: Callable[..., list[RawMetric]]) -> Callable[..., Any]:
    def parse_line(self: BaseParser, line: str, ctx: ParserContext) -> list[RawMetric]:
        if not _from_a_test():
            return original(self, line, ctx)
        seq = _sequence(ctx)
        before = ctx.extra.pop(LINE_CLAIMED, None)
        at = ctx.seq
        out = original(self, line, ctx)
        claimed = bool(ctx.extra.get(LINE_CLAIMED))
        if before is not None and not claimed:
            ctx.extra[LINE_CLAIMED] = before
        if seq is not None:
            seq["events"].append(
                {
                    "parser": self.name,
                    "seq": at,
                    "line": line,
                    "out": _metrics(out),
                    "claimed": claimed,
                    "state": _state(ctx),
                }
            )
        return out

    return parse_line


def _wrap_flush(original: Callable[..., list[RawMetric]]) -> Callable[..., Any]:
    def flush(self: BaseParser, ctx: ParserContext) -> list[RawMetric]:
        if not _from_a_test():
            return original(self, ctx)
        seq = _sequence(ctx)
        out = original(self, ctx)
        if seq is not None:
            seq["events"].append({"parser": self.name, "flush": True, "out": _metrics(out)})
        return out

    return flush


def _wrap_sniff(original: Callable[..., float]) -> Callable[..., Any]:
    def sniff(self: BaseParser, sample_lines: list[str]) -> float:
        score = original(self, sample_lines)
        if _from_a_test() and _current is not None:
            _tests.setdefault(_current, []).append(
                {"sniff": self.name, "lines": list(sample_lines), "score": score}
            )
        return score

    return sniff


def pytest_configure(config: pytest.Config) -> None:
    for cls in PORTED:
        setattr(cls, "parse_line", _wrap_parse(cls.parse_line))  # noqa: B010
        setattr(cls, "sniff", _wrap_sniff(cls.sniff))  # noqa: B010
        if hasattr(cls, "flush"):
            setattr(cls, "flush", _wrap_flush(cls.flush))  # noqa: B010


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Iterator[None]:
    global _current
    _current = item.nodeid
    yield
    _current = None
    _open.clear()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    out = os.environ.get("EPOCHIX_PARSER_RECORDING")
    if not out:
        return
    # A context that never reached a parser from a test leaves nothing.
    recorded = {
        node: [s for s in seqs if "sniff" in s or s["events"]] for node, seqs in _tests.items()
    }
    recorded = {node: seqs for node, seqs in recorded.items() if seqs}
    Path(out).write_text(
        json.dumps({"tests": recorded, "skipped": _skipped}, ensure_ascii=False),
        encoding="utf-8",
    )
