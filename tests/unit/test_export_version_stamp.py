"""An exported page must name the epochix that wrote it.

The dashboard's "report a problem" button asks the server for a version, and an
HTML export has no server — so every report filed from an exported page said
"epochix (unavailable)", the one field that decides whether a bug is already
fixed. The version is stamped into the embedded payload instead.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from epochix import __version__, parse
from epochix.exporters.json_export import build_json_payload
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path

_LINES = [
    "Epoch 1/3 - loss: 0.9000 - val_accuracy: 0.6100",
    "Epoch 2/3 - loss: 0.7000 - val_accuracy: 0.6800",
    "Epoch 3/3 - loss: 0.5000 - val_accuracy: 0.7400",
]


def _run(tmp_path: Path) -> tuple[str, str]:
    log = tmp_path / "r.log"
    log.write_text("\n".join(_LINES) + "\n", encoding="utf-8")
    db = str(tmp_path / "r.db")
    run = parse(log, db=db, run_name="r")
    return run.id, db


def test_the_json_payload_carries_the_version(tmp_path: Path) -> None:
    run_id, db = _run(tmp_path)
    payload = build_json_payload(run_id, RunStore(db_path=db))
    assert payload["epochix_version"] == __version__


def test_the_html_export_embeds_it(tmp_path: Path) -> None:
    from epochix.exporters.html_export import build_html

    run_id, db = _run(tmp_path)
    html = build_html(run_id, RunStore(db_path=db))
    match = re.search(r'<script type="application/json" id="run-data">(.*?)</script>', html, re.S)
    assert match, "no embedded run data in the export"
    assert json.loads(match.group(1))["epochix_version"] == __version__


def test_it_does_not_disturb_the_rest_of_the_payload(tmp_path: Path) -> None:
    """The payload round-trips; the stamp is an addition, not a reshape."""
    from epochix.models import Run

    run_id, db = _run(tmp_path)
    payload = build_json_payload(run_id, RunStore(db_path=db))
    assert set(payload) == {"epochix_version", "run", "frames", "events"}
    Run.model_validate(payload["run"])
    assert len(payload["frames"]) == 3
