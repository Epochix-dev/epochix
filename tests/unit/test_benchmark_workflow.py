"""The benchmark job fails when the benchmarks crash, and the benchmarks run.

`pytest tests/benchmarks/ ... || true` hid all seven erroring at setup under
pytest 9.2: the job that ran them passed, and all that showed was a missing
artifact in the next one. That job only runs for some paths, so a dependency
update reached it last; running them here shows it on every change.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "benchmarks.yml"


def test_the_job_does_not_swallow_a_failure() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pytest tests/benchmarks/" in text, "the job no longer runs them"
    assert "|| true" not in text


def test_a_change_to_the_job_runs_the_job() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert '- ".github/workflows/benchmarks.yml"' in text
    assert '- "tests/benchmarks/**"' in text
    assert '- "scripts/compare_benchmarks.py"' in text


def test_the_comparison_measures_the_base_branch() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event.pull_request.base.sha" in text
    assert "scripts/compare_benchmarks.py --base-src" in text


def test_every_benchmark_runs_on_the_installed_pytest(tmp_path: Path) -> None:
    out = tmp_path / "benchmarks.json"
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/benchmarks",
            "--benchmark-min-rounds=1",
            "--benchmark-max-time=0.001",
            f"--benchmark-json={out}",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout[-2000:]
    ran = {b["name"] for b in json.loads(out.read_text(encoding="utf-8"))["benchmarks"]}
    assert "test_universal_throughput" in ran
    assert "test_metric_event_write_throughput" in ran
