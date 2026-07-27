"""CLI usability findings from the cold-start report.

Neither was a crash in the product logic — both were the CLI being unhelpful at
exactly the moment a newcomer needed help:

* ``epochix run --export`` had no ``--output``. It wrote ``<run_id>.<fmt>``
  into the current directory and printed a relative path, so people could not
  find the file they had just been told was written.
* A port collision surfaced as a raw ``OSError`` traceback from a background
  asyncio task, with no mention of ``--port``.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _training_log(tmp_path: Path) -> Path:
    log = tmp_path / "train.log"
    log.write_text(
        "\n".join(
            f"Epoch {i}/5 train_loss={0.6 - i * 0.08:.4f} val_acc={0.7 + i * 0.03:.4f}"
            for i in range(1, 6)
        )
        + "\n",
        encoding="utf-8",
    )
    return log


def _run_cli(*args: str, cwd: Path, db: Path) -> subprocess.CompletedProcess[str]:
    import os

    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "epochix", *args],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(cwd),
        env={**os.environ, "EPOCHIX_DB": str(db)},
        check=False,
    )


def test_export_output_writes_where_asked(tmp_path: Path) -> None:
    out = tmp_path / "reports" / "run.md"
    result = _run_cli(
        "run",
        str(_training_log(tmp_path)),
        "--headless",
        "--export",
        "md",
        "--output",
        str(out),
        cwd=tmp_path,
        db=tmp_path / "runs.db",
    )
    assert result.returncode == 0, result.stderr
    assert out.exists(), f"--output was ignored; stderr: {result.stderr}"
    assert out.stat().st_size > 0


def test_export_reports_an_absolute_path(tmp_path: Path) -> None:
    """ "Exporting MD -> 01K….md" gave no clue where the file landed."""
    result = _run_cli(
        "run",
        str(_training_log(tmp_path)),
        "--headless",
        "--export",
        "json",
        cwd=tmp_path,
        db=tmp_path / "runs.db",
    )
    assert result.returncode == 0, result.stderr
    line = next(ln for ln in result.stdout.splitlines() if "Exporting" in ln)
    assert str(tmp_path) in line, f"path is not absolute: {line!r}"


def test_a_busy_port_is_explained_not_traced(tmp_path: Path) -> None:
    """The message must name the port and point at --port, with no traceback."""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    busy = holder.getsockname()[1]
    try:
        result = _run_cli(
            "serve",
            "--port",
            str(busy),
            cwd=tmp_path,
            db=tmp_path / "runs.db",
        )
    finally:
        holder.close()

    assert result.returncode == 1, result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    assert str(busy) in result.stderr
    assert "--port" in result.stderr, result.stderr
