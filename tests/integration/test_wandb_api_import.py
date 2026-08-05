"""The W&B API import path, without needing a W&B account.

Everything except the network call is real: `import_wandb` is driven against a
stub `wandb` module, so the history handling, epoch derivation and reporter
wiring are exercised for the first time.

The bug that motivated this: the importer called `run.history()`, which takes
`samples=500` and returns a DOWNSAMPLE — its own docstring says "if you are ok
with the history records being sampled". A 2000-epoch run imported as 500
points presented as the run, moving the final value, the peak and the
best-epoch call. `scan_history()` returns every record.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from epochix.integrations import wandb_import

EPOCHS = 2000


class _StubRun:
    """Mimics wandb's public Run for the two members the importer touches."""

    name = "big-run"

    def __init__(self) -> None:
        self.history_calls = 0
        self.scan_calls = 0

    def history(self, **_: Any) -> list[dict[str, float]]:
        self.history_calls += 1
        raise AssertionError("history() samples; the importer must use scan_history()")

    def scan_history(self, keys: list[str] | None = None, **_: Any) -> list[dict[str, float]]:
        self.scan_calls += 1
        return [
            {"_step": i, "epoch": i + 1, "val_accuracy": 0.5 + i * 0.0002, "train_loss": 1.0}
            for i in range(EPOCHS)
        ]


@pytest.fixture
def stub_wandb(monkeypatch: pytest.MonkeyPatch) -> _StubRun:
    run = _StubRun()

    class _Api:
        def run(self, _path: str) -> _StubRun:
            return run

    module = types.ModuleType("wandb")
    module.Api = _Api  # type: ignore[attr-defined]
    module.login = lambda **_: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "wandb", module)
    return run


def test_every_logged_step_is_imported(
    stub_wandb: _StubRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 2000-epoch run must import 2000 points, not 500."""
    logged: list[dict[str, float]] = []

    class _Reporter:
        _run_id = "01TESTRUNID"

        def __init__(self, **_: Any) -> None: ...
        def __enter__(self) -> _Reporter:
            return self

        def __exit__(self, *_: object) -> None: ...
        def log(self, **metrics: float) -> None:
            logged.append(metrics)

    import epochix.sdk.live_reporter as lr

    monkeypatch.setattr(lr, "LiveReporter", _Reporter)

    result = wandb_import.import_wandb(entity="e", project="p", run_id="r", open_browser=False)

    assert result == "01TESTRUNID"
    assert stub_wandb.scan_calls == 1
    assert stub_wandb.history_calls == 0, "sampled history() must not be used"
    assert len(logged) == EPOCHS, f"imported {len(logged)} of {EPOCHS} steps"
    # The last point must be the real last point — the sampled path moved it.
    assert logged[-1]["epoch"] == float(EPOCHS)
    # W&B bookkeeping must not arrive as a metric.
    assert not [k for k in logged[0] if k.startswith("_")]
