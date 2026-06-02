"""Parser throughput benchmarks.

Target: ≥ 50,000 lines/sec for every framework parser.

Run with::

    pytest tests/benchmarks/ -v --benchmark-min-rounds=5
"""

from __future__ import annotations

import pytest

from epochix.parsers.base import ParserContext
from epochix.parsers.huggingface import HFParser
from epochix.parsers.keras_tensorflow import KerasParser
from epochix.parsers.pytorch_lightning import PLParser
from epochix.parsers.ultralytics_yolo import YOLOParser
from epochix.parsers.universal import UniversalParser

# ── Sample lines for each parser ─────────────────────────────────────────────

PL_LINE = (
    "Epoch 5/50: 100%|=====>| 250/250 [00:12<00:00, "
    "loss=0.432, acc=0.867, val_loss=0.401, val_acc=0.874]"
)
KERAS_EPOCH = "Epoch 5/50"
KERAS_METRIC = (
    "1563/1563 [==============================>] - 10s 6ms/step "
    "- loss: 0.423 - accuracy: 0.867 - val_loss: 0.401 - val_accuracy: 0.874"
)
HF_TRAIN = "{'loss': 0.5123, 'learning_rate': 5e-05, 'epoch': 1.0}"
HF_EVAL = "{'eval_loss': 0.3421, 'eval_accuracy': 0.8765, 'epoch': 1.0}"
YOLO_TRAIN = "      5/50     1.23G   0.456   0.234   0.123   128"
YOLO_VAL = "                 all       5000       5000   0.712   0.654   0.678   0.432"
UNIVERSAL_LINE = (
    "[Epoch 5/50] train_loss=0.432 train_acc=0.867 val_loss=0.401 val_accuracy=0.874 lr=0.001"
)


def _make_ctx() -> ParserContext:
    return ParserContext(run_id="benchmark", seq=0)


# ── Benchmarks ────────────────────────────────────────────────────────────────

# Advisory throughput reference (lines/sec). NOT asserted here: the per-call
# pytest-benchmark harness adds fixture overhead and is load-sensitive, so an
# absolute floor flakes near the boundary (esp. the universal parser). The hard
# >= 50k gate lives in scripts/benchmark-parsers.py (a tight loop with real
# headroom), which is the step benchmarks.yml actually fails on. These tests
# record throughput for the JSON artifact + base-branch comparison instead.
ADVISORY_LPS = 50_000


def _report(name: str, benchmark: pytest.FixtureType, capsys: pytest.CaptureFixture[str]) -> None:
    lps = 1.0 / benchmark.stats["mean"]
    with capsys.disabled():
        flag = "" if lps >= ADVISORY_LPS else f"  (below advisory {ADVISORY_LPS:,}/s)"
        print(f"\n{name} throughput: {lps:,.0f} lines/sec{flag}")


@pytest.mark.benchmark(group="parsers")
def test_pytorch_lightning_throughput(
    benchmark: pytest.FixtureType, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = PLParser()
    ctx = _make_ctx()
    n = 0

    def _parse_one() -> None:
        nonlocal n
        ctx.seq += 1
        n += 1
        parser.parse_line(PL_LINE, ctx)

    benchmark(_parse_one)
    _report("PLParser", benchmark, capsys)
    assert n > 0


@pytest.mark.benchmark(group="parsers")
def test_keras_throughput(
    benchmark: pytest.FixtureType, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = KerasParser()
    ctx = _make_ctx()
    lines = [KERAS_EPOCH, KERAS_METRIC]
    idx = 0

    def _parse_one() -> None:
        nonlocal idx
        ctx.seq += 1
        parser.parse_line(lines[idx % 2], ctx)
        idx += 1

    benchmark(_parse_one)
    _report("KerasParser", benchmark, capsys)
    assert idx > 0


@pytest.mark.benchmark(group="parsers")
def test_huggingface_throughput(
    benchmark: pytest.FixtureType, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = HFParser()
    ctx = _make_ctx()
    lines = [HF_TRAIN, HF_EVAL]
    idx = 0

    def _parse_one() -> None:
        nonlocal idx
        ctx.seq += 1
        parser.parse_line(lines[idx % 2], ctx)
        idx += 1

    benchmark(_parse_one)
    _report("HFParser", benchmark, capsys)
    assert idx > 0


@pytest.mark.benchmark(group="parsers")
def test_yolo_throughput(benchmark: pytest.FixtureType, capsys: pytest.CaptureFixture[str]) -> None:
    parser = YOLOParser()
    ctx = _make_ctx()
    lines = [YOLO_TRAIN, YOLO_VAL]
    idx = 0

    def _parse_one() -> None:
        nonlocal idx
        ctx.seq += 1
        parser.parse_line(lines[idx % 2], ctx)
        idx += 1

    benchmark(_parse_one)
    _report("YOLOParser", benchmark, capsys)
    assert idx > 0


@pytest.mark.benchmark(group="parsers")
def test_universal_throughput(
    benchmark: pytest.FixtureType, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = UniversalParser()
    ctx = _make_ctx()
    n = 0

    def _parse_one() -> None:
        nonlocal n
        ctx.seq += 1
        n += 1
        parser.parse_line(UNIVERSAL_LINE, ctx)

    benchmark(_parse_one)
    _report("UniversalParser", benchmark, capsys)
    assert n > 0
