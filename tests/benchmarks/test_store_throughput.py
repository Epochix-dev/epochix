"""Store throughput benchmarks.

Target: ≥ 10,000 MetricEvent writes/sec.

Run with::

    pytest tests/benchmarks/ -v --benchmark-min-rounds=5
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from epochix.enums import TaskType
from epochix.models import MetricEvent, Run
from epochix.store.sqlite_store import RunStore


def _make_store() -> RunStore:
    return RunStore(":memory:")


def _make_run(store: RunStore) -> str:
    run = Run(
        id="bench-run-01",
        task_type=TaskType.CLASSIFICATION,
        started_at=datetime.now(timezone.utc),
        primary_metric="val_accuracy",
        parser_used="pytorch_lightning",
    )
    store.create_run(run)
    return run.id


def _make_event(run_id: str, seq: int) -> MetricEvent:
    return MetricEvent(
        run_id=run_id,
        seq=seq,
        timestamp=datetime.now(timezone.utc),
        canonical_key="val_accuracy",
        raw_key="val_acc",
        value=0.5 + seq * 0.001,
    )


# ── Benchmarks ────────────────────────────────────────────────────────────────

# Advisory throughput reference (writes/sec). NOT asserted: single-row commit
# rate is hardware-dependent and a hard floor flakes near the boundary across
# machines. Regressions are tracked via the recorded benchmark JSON + the
# base-branch comparison in benchmarks.yml, not a per-run pass/fail gate.
ADVISORY_WPS = 10_000


@pytest.mark.benchmark(group="store")
def test_metric_event_write_throughput(
    benchmark: pytest.FixtureType, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _make_store()
    run_id = _make_run(store)
    seq = 0

    def _write_one() -> None:
        nonlocal seq
        seq += 1
        store.append_metric_event(_make_event(run_id, seq))

    benchmark(_write_one)
    wps = 1.0 / benchmark.stats["mean"]
    with capsys.disabled():
        flag = "" if wps >= ADVISORY_WPS else f"  (below advisory {ADVISORY_WPS:,}/s)"
        print(f"\nRunStore write throughput: {wps:,.0f} writes/sec{flag}")
    # Sanity only: the write path actually persisted events (no perf gate).
    assert seq > 0


@pytest.mark.benchmark(group="store")
def test_run_list_throughput(benchmark: pytest.FixtureType) -> None:
    """Listing runs should be fast even with many runs."""
    store = _make_store()
    # Pre-populate 100 runs
    for i in range(100):
        run = Run(
            id=f"run-{i:04d}",
            task_type=TaskType.CLASSIFICATION,
            started_at=datetime.now(timezone.utc),
            primary_metric="val_accuracy",
            parser_used="pytorch_lightning",
        )
        store.create_run(run)

    result = benchmark(store.list_runs)
    # Just verify it completes quickly (no hard target for reads)
    assert len(result) == 100
