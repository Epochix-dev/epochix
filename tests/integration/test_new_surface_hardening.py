"""Adversarial pass over the surfaces added in 0.5.79–0.5.88.

Each case here is a bug that was live, found by feeding the new commands the
inputs a real user hits on a bad day: a missing optional dependency, a
half-written file, two flags used together.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONIOENCODING": "utf-8",
        "EPOCHIX_DB": str(cwd / "t.db"),
        "PATH": "",
        "SYSTEMROOT": "C:\\Windows",
    }
    return subprocess.run(
        [sys.executable, "-m", "epochix.cli", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )


@pytest.fixture
def log(tmp_path: Path) -> Path:
    lines = [
        f"Epoch {i}/8 loss: {1.4 - i * 0.1:.4f} val_accuracy: {0.55 + i * 0.04:.4f}"
        for i in range(1, 9)
    ]
    p = tmp_path / "train.log"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_json_and_export_together_still_emit_one_clean_document(log: Path, tmp_path: Path) -> None:
    """`--json --export md` printed the export line AFTER the JSON.

    stdout became `{...}\\n  Exporting MD -> ...`, so json.load died on "Extra
    data: line 2". The 0.5.80 guard covered the line printed BEFORE the
    document and missed the one after. Informational output now goes to
    stderr when stdout is carrying JSON — redirected, not silenced.
    """
    out = tmp_path / "r.md"
    res = _cli("run", str(log), "--json", "--export", "md", "--output", str(out), cwd=tmp_path)

    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)  # the actual assertion: it parses
    assert payload["id"]
    assert out.is_file() and out.stat().st_size > 0, "export must still be written"
    # The chatter must still reach the user, just not on stdout.
    assert "Exporting" in res.stderr


def test_json_survives_a_log_with_nothing_parseable(tmp_path: Path) -> None:
    """No metrics is not a crash: automation still needs a parseable answer."""
    junk = tmp_path / "junk.log"
    junk.write_text("hello world\nnothing to see\n", encoding="utf-8")

    res = _cli("run", str(junk), "--json", cwd=tmp_path)

    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout)
    assert payload["final_grade"] is None


def test_import_wandb_on_an_unreadable_file_says_so(tmp_path: Path) -> None:
    """A truncated `.wandb` raised "Invalid header" as a raw traceback.

    Not exotic — a RUNNING job has one being written.
    """
    d = tmp_path / "wandb" / "run-bad"
    d.mkdir(parents=True)
    (d / "run-bad.wandb").write_bytes(b"definitely not a wandb record log")

    res = _cli("import-wandb", str(tmp_path / "wandb"), "--headless", cwd=tmp_path)

    assert res.returncode != 0
    combined = res.stdout + res.stderr
    assert "Traceback" not in combined, combined[:400]
    assert "No run history found" in combined or "Skipping" in combined


def test_import_wandb_rejects_a_malformed_reference(tmp_path: Path) -> None:
    res = _cli("import-wandb", "only/two", "--headless", cwd=tmp_path)
    assert res.returncode == 2
    assert "entity/project/run_id" in res.stdout + res.stderr


def test_import_tensorboard_on_a_missing_directory(tmp_path: Path) -> None:
    res = _cli("import-tensorboard", str(tmp_path / "nope"), "--headless", cwd=tmp_path)
    assert res.returncode == 1
    assert "not found" in (res.stdout + res.stderr).lower()
