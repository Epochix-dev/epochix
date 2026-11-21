"""`python train.py | epochix` — the first command in the README — run for real.

Coverage, measured for the first time on 2026-11-10, showed that no test read
a line from standard input: `StdinIngester.lines` and both of its readers (a
pipe on Unix, a thread on Windows) had never run. `make_ingester` was asserted
to return the class, and that was all.

So this pipes a recorded log into the CLI, and the story told must be the one
`corpus_truth.json` records for that log read as a file.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from epochix.store.sqlite_store import RunStore

ROOT = Path(__file__).resolve().parents[2]
LOG = "pytorch_lightning.log"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_a_piped_log_is_told_as_the_same_story_as_the_file(tmp_path: Path) -> None:
    truth = json.loads((ROOT / "tests/fixtures/corpus_truth.json").read_text(encoding="utf-8"))[LOG]
    text = (ROOT / truth["path"]).read_text(encoding="utf-8")
    db = tmp_path / "runs.db"

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "epochix", "--json", "--port", str(_free_port())],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        cwd=str(tmp_path),
        env={
            **os.environ,
            "EPOCHIX_DB": str(db),
            "EPOCHIX_GRADE_CONFIG": "off",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(ROOT / "src"),
        },
        check=False,
    )
    assert result.returncode == 0, result.stderr

    summary = json.loads(result.stdout)
    assert summary["task"] == truth["task"]
    assert summary["primary_metric"] == truth["metric"]
    assert summary["final_grade"] == truth["final_grade"]

    # And it was stored as read: the last value of the story's metric.
    store = RunStore(db_path=str(db))
    frames = store.get_story_frames(summary["id"])
    assert frames, "the piped run was stored without a single frame"
    assert frames[-1].primary_metric == truth["metric"]
    assert frames[-1].primary_metric_value == truth["last_value"]
