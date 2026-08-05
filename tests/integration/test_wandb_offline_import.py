"""Reading a W&B run off local disk — no account, no key, no network.

`import_wandb` talks to the W&B API and so needs credentials, which put the
strongest thing epochix can say to a W&B user ("point it at the runs you
already have") behind a login. `import_wandb_dir` reads the run directory
instead.

The fixture is a REAL file: produced by `wandb.init()` under
`WANDB_MODE=offline`, not hand-written. The layout was not what it looked like
from the outside — there is no `wandb-summary.json` and no `output.log`, the
history lives only in the binary `run-*.wandb`, and history items carry their
name in `nested_key` rather than `key`. A fabricated fixture would have encoded
those wrong assumptions and passed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("wandb", reason="offline import reads the file with wandb's own DataStore")

from epochix.integrations.wandb_import import _scan_wandb_file  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "wandb_offline"
RUN_FILE = FIXTURE / "run-bx0dl6kg.wandb"


def test_fixture_is_present() -> None:
    """Guard the guard — a missing fixture must fail, not silently skip."""
    assert RUN_FILE.is_file(), f"missing fixture: {RUN_FILE}"


def test_reads_the_full_history_without_credentials() -> None:
    name, rows = _scan_wandb_file(RUN_FILE)

    assert name == "offline-run"
    # The run logged 12 epochs.
    assert len(rows) == 12
    assert rows[0] == pytest.approx({"val_accuracy": 0.445, "train_loss": 1.49, "epoch": 1.0})
    assert rows[-1]["epoch"] == 12.0
    assert rows[-1]["val_accuracy"] == pytest.approx(0.94)


def test_bookkeeping_columns_are_not_imported_as_metrics() -> None:
    """`_step`, `_runtime` and `_timestamp` are W&B internals, not results.

    Importing them would put a wall-clock timestamp on the chart as though it
    were something the model achieved.
    """
    _, rows = _scan_wandb_file(RUN_FILE)
    for row in rows:
        assert not [k for k in row if k.startswith("_")], row


def test_epoch_is_carried_through() -> None:
    """Without an epoch the dashboard shows "Epoch —" and a dead progress bar."""
    _, rows = _scan_wandb_file(RUN_FILE)
    assert [r["epoch"] for r in rows] == [float(i) for i in range(1, 13)]
