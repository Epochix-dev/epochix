"""The %epochix Jupyter magics, driven through a REAL IPython shell.

docs/quickstart.md tells people to run `%load_ext epochix`, but nothing ever
executed it. Four bugs shipped behind that gap:

* `%load_ext epochix` printed "The epochix module is not an IPython extension"
  and registered no magics at all — IPython looks for load_ipython_extension on
  the module you name, and it only existed on epochix.integrations.jupyter.
* `%epochix <log>` parsed into the default db=":memory:", so the run was thrown
  away and the iframe pointed at a run the server had never heard of.
* `%%epochix --live` pushed a fabricated `raw=0.0` metric per output line and
  never fed the script's real output to the parser.
* `%%epochix --live` also started a second server on the port LiveReporter was
  already binding, so uvicorn failed to start and killed the reporter thread.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from epochix.enums import TaskType
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path

pytest.importorskip("IPython")


def _log(tmp_path: Path) -> Path:
    path = tmp_path / "train.log"
    path.write_text(
        "".join(
            f"Epoch {e}/6 train_loss={1.6 - e * 0.2:.3f} val_accuracy={0.5 + e * 0.06:.3f}\n"
            for e in range(1, 7)
        ),
        encoding="utf-8",
    )
    return path


def test_load_ext_epochix_registers_the_magics() -> None:
    """`%load_ext epochix` — the exact line in the quickstart — must work."""
    from IPython.core.interactiveshell import InteractiveShell

    shell = InteractiveShell.instance()
    shell.run_line_magic("load_ext", "epochix")

    assert "epochix" in shell.magics_manager.magics["line"], "%epochix not registered"
    assert "epochix" in shell.magics_manager.magics["cell"], "%%epochix not registered"


def test_line_magic_parses_into_the_db_the_server_serves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parsed run has to land in the served DB, or the iframe is empty."""
    db = str(tmp_path / "runs.db")
    monkeypatch.setenv("EPOCHIX_DB", db)

    from epochix.integrations.jupyter import _parse_and_register

    run = _parse_and_register(_log(tmp_path), task=None, port=7860)

    assert run.id
    stored = RunStore(db_path=db).list_runs()
    assert len(stored) == 1, "the run is not in the DB the dashboard reads"
    assert stored[0].id == run.id
    assert stored[0].task_type == TaskType.CLASSIFICATION
    assert stored[0].name, "the run should be named after the log file"


def test_log_line_feeds_real_output_to_the_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LiveReporter.log_line() is what the cell magic relays stdout through.

    The magic used to call log(raw=0.0) per line instead — a fabricated
    heartbeat — so a live cell produced a run with no real metrics in it.
    """
    monkeypatch.setenv("EPOCHIX_DB", str(tmp_path / "runs.db"))

    from epochix.sdk.live_reporter import LiveReporter

    reporter = LiveReporter(task="classification", name="cell", open_browser=False, port=0)
    with reporter:
        for e in range(1, 5):
            reporter.log_line(
                f"Epoch {e}/4 train_loss={2.0 - e * 0.3:.3f} val_accuracy={0.4 + e * 0.09:.3f}"
            )

    store = RunStore(db_path=str(tmp_path / "runs.db"))
    runs = store.list_runs()
    assert len(runs) == 1
    metrics = store.get_metric_events(runs[0].id)
    keys = {m.canonical_key for m in metrics}

    assert "val_accuracy" in keys and "train_loss" in keys, (
        f"the raw lines were not parsed into real metrics: {keys}"
    )
    assert keys != {"custom"}, "only fabricated/heartbeat metrics were stored"
    accs = sorted(m.value for m in metrics if m.canonical_key == "val_accuracy")
    assert accs == pytest.approx([0.49, 0.58, 0.67, 0.76]), accs
