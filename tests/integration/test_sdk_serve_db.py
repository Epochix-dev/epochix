"""epochix.serve(db=...) and epochix.visualize(run, db=...) serve the database given.

Neither did. `serve` never read its `db` argument; `visualize` opened a store
on it and set it on the app, and the app's startup replaced that store with
one on EPOCHIX_DB. So `visualize(run, db=...)` opened a dashboard on a run the
server it started could not find. Both now give the app settings naming that
database, which is what its startup opens.

Each case runs the SDK call in its own process — the real server, the real
startup — with EPOCHIX_DB pointing somewhere else.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

LOG = Path(__file__).parents[1] / "fixtures" / "logs" / "keras_50ep.log"

CALLS = {
    "serve": "epochix.serve(port=PORT, db=DB, open_browser=False)",
    "visualize": "epochix.visualize(run, port=PORT, db=DB)",
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def _get(port: int, path: str) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:  # noqa: S310
            return r.status, json.load(r)
    except urllib.error.HTTPError as exc:
        return exc.code, None


@pytest.mark.parametrize("call", sorted(CALLS))
def test_the_sdk_serves_the_database_it_is_given(tmp_path: Path, call: str) -> None:
    given = tmp_path / "given.db"
    port = _free_port()
    script = (
        "import epochix\n"
        f"DB = {str(given)!r}\n"
        f"run = epochix.parse({str(LOG)!r}, db=DB)\n"
        "print('RUN', run.id, flush=True)\n" + CALLS[call].replace("PORT", str(port)) + "\n"
    )
    env = {
        **os.environ,
        "EPOCHIX_DB": str(tmp_path / "elsewhere.db"),
        "EPOCHIX_OPEN_BROWSER": "false",
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.Popen(  # noqa: S603 — this package's own code
        [sys.executable, "-u", "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        env=env,
    )
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline()
        assert line.startswith("RUN "), line
        run_id = line.split()[1]

        deadline = time.monotonic() + 30
        while True:
            try:
                status, body = _get(port, "/api/runs")
                break
            except OSError:
                assert proc.poll() is None, "the SDK call exited"
                assert time.monotonic() < deadline, f"nothing answered on {port}"
                time.sleep(0.1)
        assert status == 200
        assert isinstance(body, dict)
        assert [r["id"] for r in body["runs"]] == [run_id]
        # The page visualize() opens is /v/<run_id>; this is what it reads.
        assert _get(port, f"/api/snapshot/{run_id}")[0] == 200
    finally:
        proc.kill()
        proc.communicate(timeout=10)
