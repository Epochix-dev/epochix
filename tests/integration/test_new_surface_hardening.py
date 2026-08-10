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


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    # Every server-starting command gets an explicitly free port. Relying on
    # the 7860 default made these pass on CI and fail on any machine with a
    # dashboard already open — including this one, where an orphaned
    # `epochix serve` was holding it. A test must not depend on a port nobody
    # promised was free.
    if args and args[0] in {"run", "import-wandb", "import-tensorboard"} and "--port" not in args:
        args = (*args, "--port", str(_free_port()))

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

    # The invariant is the same either way: a sentence, never a traceback.
    # Which sentence depends on the machine — CI installs no optional extras,
    # so it hits "wandb is required" before it can even open the file, while a
    # developer with wandb installed hits "Invalid header" and skips the file.
    # Asserting only one of those made this test pass locally and fail on CI.
    assert "Traceback" not in combined, combined[:400]
    assert any(
        phrase in combined for phrase in ("No run history found", "Skipping", "wandb is required")
    ), combined[:400]


def test_import_wandb_rejects_a_malformed_reference(tmp_path: Path) -> None:
    res = _cli("import-wandb", "only/two", "--headless", cwd=tmp_path)
    assert res.returncode == 2
    assert "entity/project/run_id" in res.stdout + res.stderr


def test_import_tensorboard_on_a_missing_directory(tmp_path: Path) -> None:
    res = _cli("import-tensorboard", str(tmp_path / "nope"), "--headless", cwd=tmp_path)
    assert res.returncode == 1
    assert "not found" in (res.stdout + res.stderr).lower()


def test_import_commands_report_a_busy_port_instead_of_a_traceback(tmp_path: Path) -> None:
    """Both importers start their own server through LiveReporter.

    A bind failure happens inside a background asyncio task, so it surfaced as
    a raw uvicorn traceback and SystemExit(3) rather than a message. `run` has
    guarded this since 0.5.32; the import commands were added without it — and
    the likeliest reason the default port is taken is that the user already has
    an epochix dashboard open, which is exactly who runs these.
    """
    import socket

    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        busy = held.getsockname()[1]

        d = tmp_path / "wandb" / "run-x"
        d.mkdir(parents=True)
        (d / "run-x.wandb").write_bytes(b"x")

        for args in (
            ("import-wandb", str(tmp_path / "wandb")),
            ("import-tensorboard", str(tmp_path)),
        ):
            res = _cli(*args, "--port", str(busy), "--headless", cwd=tmp_path)
            combined = res.stdout + res.stderr
            assert "Traceback" not in combined, f"{args[0]}: {combined[:300]}"
            assert "already in use" in combined, f"{args[0]}: {combined[:300]}"
